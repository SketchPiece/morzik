// Morzik Bridge: Apple Calendar and Reminders over MCP (streamable HTTP, JSON responses).
// Runs on the Mac as a LaunchAgent; Morzik reaches it at /mcp with a bearer token.

import EventKit
import Foundation
import Network

// MARK: - Config

let env = ProcessInfo.processInfo.environment
let configDir = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".config/morzik-bridge")
let host = env["MORZIK_BRIDGE_HOST"] ?? "127.0.0.1"
let port = UInt16(env["MORZIK_BRIDGE_PORT"] ?? "") ?? 8765
let token: String = {
    if let t = env["MORZIK_BRIDGE_TOKEN"], !t.isEmpty { return t }
    let file = configDir.appendingPathComponent("token")
    let t = (try? String(contentsOf: file, encoding: .utf8))?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    if t.isEmpty { fatalError("no token: set MORZIK_BRIDGE_TOKEN or write \(file.path)") }
    return t
}()

func log(_ s: String) {
    FileHandle.standardError.write("[\(ISO8601DateFormatter().string(from: Date()))] \(s)\n".data(using: .utf8)!)
}

// MARK: - EventKit

let store = EKEventStore()
let ekQueue = DispatchQueue(label: "morzik-bridge.eventkit")

func requestAccess() {
    let sem = DispatchSemaphore(value: 0)
    store.requestFullAccessToEvents { ok, err in
        log("calendar access: \(ok) \(err.map { "\($0)" } ?? "")"); sem.signal()
    }
    sem.wait()
    store.requestFullAccessToReminders { ok, err in
        log("reminders access: \(ok) \(err.map { "\($0)" } ?? "")"); sem.signal()
    }
    sem.wait()
}

func accessStatus(_ type: EKEntityType) -> String {
    switch EKEventStore.authorizationStatus(for: type) {
    case .fullAccess: return "full"
    case .writeOnly: return "write-only"
    case .denied: return "denied"
    case .restricted: return "restricted"
    case .notDetermined: return "not determined"
    @unknown default: return "unknown"
    }
}

struct ToolError: Error { let message: String }

// MARK: - Dates

let tz = TimeZone.current

func formatter(_ f: String) -> DateFormatter {
    let d = DateFormatter()
    d.locale = Locale(identifier: "en_US_POSIX")
    d.timeZone = tz
    d.dateFormat = f
    return d
}

let localFormats = ["yyyy-MM-dd'T'HH:mm:ss", "yyyy-MM-dd'T'HH:mm", "yyyy-MM-dd HH:mm:ss", "yyyy-MM-dd HH:mm"].map(formatter)
let dayFormat = formatter("yyyy-MM-dd")
let outFormat = formatter("yyyy-MM-dd'T'HH:mm:ssxxx")

/// Parses ISO 8601. Without an offset the time is the Mac's local time. Returns hasTime=false for "YYYY-MM-DD".
func parseDate(_ s: String) throws -> (date: Date, hasTime: Bool) {
    let iso = ISO8601DateFormatter()
    iso.formatOptions = [.withInternetDateTime]
    if let d = iso.date(from: s) { return (d, true) }
    iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    if let d = iso.date(from: s) { return (d, true) }
    for f in localFormats { if let d = f.date(from: s) { return (d, true) } }
    if let d = dayFormat.date(from: s) { return (d, false) }
    throw ToolError(message: "bad date '\(s)': use ISO 8601, e.g. 2026-10-24T09:00 or 2026-10-24T09:00-07:00 or 2026-10-24")
}

func out(_ d: Date?) -> Any { d.map { outFormat.string(from: $0) } ?? NSNull() }

// MARK: - Args

struct Args {
    let raw: [String: Any]
    func str(_ k: String) -> String? { (raw[k] as? String).flatMap { $0.isEmpty ? nil : $0 } }
    func need(_ k: String) throws -> String {
        guard let v = str(k) else { throw ToolError(message: "missing '\(k)'") }
        return v
    }
    func bool(_ k: String) -> Bool? { raw[k] as? Bool }
    func int(_ k: String) -> Int? { (raw[k] as? NSNumber)?.intValue }
    func has(_ k: String) -> Bool { raw[k] != nil && !(raw[k] is NSNull) }
}

func recurrence(_ s: String?) throws -> EKRecurrenceRule? {
    guard let s else { return nil }
    let f: EKRecurrenceFrequency
    switch s {
    case "daily": f = .daily
    case "weekly": f = .weekly
    case "monthly": f = .monthly
    case "yearly": f = .yearly
    case "none": return nil
    default: throw ToolError(message: "recurrence must be daily, weekly, monthly, yearly or none")
    }
    return EKRecurrenceRule(recurrenceWith: f, interval: 1, end: nil)
}

func recurrenceName(_ item: EKCalendarItem) -> Any {
    guard let r = item.recurrenceRules?.first else { return NSNull() }
    switch r.frequency {
    case .daily: return "daily"
    case .weekly: return "weekly"
    case .monthly: return "monthly"
    case .yearly: return "yearly"
    @unknown default: return "custom"
    }
}

// MARK: - Calendar

func findCalendar(_ name: String?, _ type: EKEntityType) throws -> EKCalendar {
    let all = store.calendars(for: type)
    guard let name else {
        let def = type == .event ? store.defaultCalendarForNewEvents : store.defaultCalendarForNewReminders()
        guard let def else { throw ToolError(message: "no default \(type == .event ? "calendar" : "reminders list")") }
        return def
    }
    if let c = all.first(where: { $0.calendarIdentifier == name || $0.title == name })
        ?? all.first(where: { $0.title.localizedCaseInsensitiveCompare(name) == .orderedSame }) {
        return c
    }
    throw ToolError(message: "no \(type == .event ? "calendar" : "reminders list") '\(name)'. Have: \(all.map(\.title).joined(separator: ", "))")
}

func calendarJSON(_ c: EKCalendar, _ type: EKEntityType) -> [String: Any] {
    let def = type == .event ? store.defaultCalendarForNewEvents : store.defaultCalendarForNewReminders()
    return ["id": c.calendarIdentifier, "title": c.title, "account": c.source?.title ?? NSNull(),
            "writable": c.allowsContentModifications, "default": c.calendarIdentifier == def?.calendarIdentifier]
}

func eventJSON(_ e: EKEvent) -> [String: Any] {
    var j: [String: Any] = [
        "id": e.eventIdentifier ?? NSNull(), "title": e.title ?? "", "calendar": e.calendar?.title ?? NSNull(),
        "all_day": e.isAllDay, "location": e.location ?? NSNull(), "notes": e.notes ?? NSNull(),
        "recurrence": recurrenceName(e), "alarms_minutes_before": (e.alarms ?? []).map { Int(-$0.relativeOffset / 60) },
    ]
    if e.isAllDay {
        j["start"] = dayFormat.string(from: e.startDate)
        j["end"] = dayFormat.string(from: e.endDate)
    } else {
        j["start"] = out(e.startDate)
        j["end"] = out(e.endDate)
    }
    return j
}

func findEvent(_ id: String) throws -> EKEvent {
    guard let e = store.event(withIdentifier: id) else { throw ToolError(message: "no event with id '\(id)'") }
    return e
}

func applyEvent(_ e: EKEvent, _ a: Args, creating: Bool) throws {
    if let t = a.str("title") { e.title = t }
    if a.has("location") { e.location = a.str("location") }
    if a.has("notes") { e.notes = a.str("notes") }
    if let c = a.str("calendar") { e.calendar = try findCalendar(c, .event) }
    if let s = a.str("start") {
        let (start, hasTime) = try parseDate(s)
        let allDay = a.bool("all_day") ?? !hasTime
        e.isAllDay = allDay
        e.startDate = start
        if let en = a.str("end") {
            var end = try parseDate(en).date
            if allDay, end <= start { end = start }
            e.endDate = end
        } else {
            e.endDate = allDay ? start : start.addingTimeInterval(TimeInterval((a.int("duration_minutes") ?? 60) * 60))
        }
    } else if let en = a.str("end") {
        e.endDate = try parseDate(en).date
    } else if creating {
        throw ToolError(message: "missing 'start'")
    }
    if a.has("alarm_minutes_before") {
        e.alarms = nil
        if let m = a.int("alarm_minutes_before"), m >= 0 { e.addAlarm(EKAlarm(relativeOffset: TimeInterval(-m * 60))) }
    }
    if a.has("recurrence") {
        e.recurrenceRules = nil
        if let r = try recurrence(a.str("recurrence")) { e.addRecurrenceRule(r) }
    }
}

func span(_ a: Args) -> EKSpan { a.str("span") == "future" ? .futureEvents : .thisEvent }

// MARK: - Reminders

func fetchReminders(_ predicate: NSPredicate) -> [EKReminder] {
    let sem = DispatchSemaphore(value: 0)
    var result: [EKReminder] = []
    store.fetchReminders(matching: predicate) { r in result = r ?? []; sem.signal() }
    sem.wait()
    return result
}

func reminderJSON(_ r: EKReminder) -> [String: Any] {
    var due: Any = NSNull()
    if let c = r.dueDateComponents, let d = Calendar.current.date(from: c) {
        due = c.hour == nil ? dayFormat.string(from: d) : outFormat.string(from: d)
    }
    return ["id": r.calendarItemIdentifier, "title": r.title ?? "", "list": r.calendar?.title ?? NSNull(),
            "due": due, "notes": r.notes ?? NSNull(), "priority": r.priority, "completed": r.isCompleted,
            "completed_at": out(r.completionDate), "recurrence": recurrenceName(r)]
}

func findReminder(_ id: String) throws -> EKReminder {
    guard let r = store.calendarItem(withIdentifier: id) as? EKReminder else { throw ToolError(message: "no reminder with id '\(id)'") }
    return r
}

func applyReminder(_ r: EKReminder, _ a: Args) throws {
    if let t = a.str("title") { r.title = t }
    if a.has("notes") { r.notes = a.str("notes") }
    if let l = a.str("list") { r.calendar = try findCalendar(l, .reminder) }
    if let p = a.int("priority") { r.priority = p }
    if a.has("due") {
        r.alarms = nil
        if let s = a.str("due") {
            let (d, hasTime) = try parseDate(s)
            let units: Set<Calendar.Component> = hasTime ? [.year, .month, .day, .hour, .minute, .timeZone] : [.year, .month, .day]
            r.dueDateComponents = Calendar.current.dateComponents(units, from: d)
            if hasTime { r.addAlarm(EKAlarm(absoluteDate: d)) }  // without an alarm Reminders doesn't notify
        } else {
            r.dueDateComponents = nil
        }
    }
    if a.has("recurrence") {
        r.recurrenceRules = nil
        if let rule = try recurrence(a.str("recurrence")) {
            guard r.dueDateComponents != nil else { throw ToolError(message: "a repeating reminder needs 'due'") }
            r.addRecurrenceRule(rule)
        }
    }
}

// MARK: - Tools

typealias Handler = (Args) throws -> Any

struct Tool {
    let name: String
    let description: String
    let properties: [String: Any]
    let required: [String]
    let handler: Handler
}

func p(_ type: String, _ desc: String, _ extra: [String: Any] = [:]) -> [String: Any] {
    ["type": type, "description": desc].merging(extra) { a, _ in a }
}

let dateHint = "ISO 8601. Without an offset it's the Mac's local time (\(tz.identifier)). Date only (YYYY-MM-DD) = all day / no time."
let recurrenceProp = p("string", "Repeat: daily, weekly, monthly, yearly; none removes it.", ["enum": ["daily", "weekly", "monthly", "yearly", "none"]])

let tools: [Tool] = [
    Tool(name: "status", description: "Bridge status: access to Calendar and Reminders, the Mac's time zone and current time.",
         properties: [:], required: []) { _ in
        ["calendar_access": accessStatus(.event), "reminders_access": accessStatus(.reminder),
         "time_zone": tz.identifier, "now": outFormat.string(from: Date())]
    },

    // Calendar
    Tool(name: "calendar_list_calendars", description: "List Apple Calendar calendars (id, title, account, writable, default).",
         properties: [:], required: []) { _ in
        store.calendars(for: .event).map { calendarJSON($0, .event) }
    },
    Tool(name: "calendar_list_events", description: "Events between start and end (default: today through 7 days), optionally in one calendar or matching text.",
         properties: ["start": p("string", dateHint), "end": p("string", dateHint),
                      "calendar": p("string", "Calendar title or id."), "query": p("string", "Case-insensitive text in title, location or notes.")],
         required: []) { a in
        let start = try a.str("start").map { try parseDate($0).date } ?? Calendar.current.startOfDay(for: Date())
        let end = try a.str("end").map { try parseDate($0).date } ?? start.addingTimeInterval(7 * 86400)
        let cals = try a.str("calendar").map { [try findCalendar($0, .event)] }
        var events = store.events(matching: store.predicateForEvents(withStart: start, end: end, calendars: cals))
        if let q = a.str("query") {
            events = events.filter { e in [e.title, e.location, e.notes].contains { $0?.localizedCaseInsensitiveContains(q) == true } }
        }
        return events.sorted { $0.startDate < $1.startDate }.map(eventJSON)
    },
    Tool(name: "calendar_create_event", description: "Create a calendar event. Without 'end' it lasts duration_minutes (default 60); a date-only start makes an all-day event.",
         properties: ["title": p("string", "Event title."), "start": p("string", dateHint), "end": p("string", dateHint),
                      "duration_minutes": p("integer", "Used when 'end' is not given."), "all_day": p("boolean", "Force all-day."),
                      "calendar": p("string", "Calendar title or id; default calendar if omitted."),
                      "location": p("string", "Location."), "notes": p("string", "Notes."),
                      "alarm_minutes_before": p("integer", "Alert this many minutes before start (0 = at start)."),
                      "recurrence": recurrenceProp],
         required: ["title", "start"]) { a in
        let e = EKEvent(eventStore: store)
        e.calendar = try findCalendar(a.str("calendar"), .event)
        try applyEvent(e, a, creating: true)
        try store.save(e, span: .thisEvent, commit: true)
        return eventJSON(e)
    },
    Tool(name: "calendar_update_event", description: "Change an event by id. Only given fields change; empty string clears location/notes, alarm_minutes_before -1 removes alerts.",
         properties: ["id": p("string", "Event id."), "title": p("string", "Title."), "start": p("string", dateHint), "end": p("string", dateHint),
                      "duration_minutes": p("integer", "Used with 'start' when 'end' is not given."), "all_day": p("boolean", "All-day."),
                      "calendar": p("string", "Move to this calendar."), "location": p("string", "Location."), "notes": p("string", "Notes."),
                      "alarm_minutes_before": p("integer", "Alert minutes before; -1 removes."), "recurrence": recurrenceProp,
                      "span": p("string", "For repeating events: this (default) or future.", ["enum": ["this", "future"]])],
         required: ["id"]) { a in
        let e = try findEvent(try a.need("id"))
        try applyEvent(e, a, creating: false)
        try store.save(e, span: span(a), commit: true)
        return eventJSON(e)
    },
    Tool(name: "calendar_delete_event", description: "Delete an event by id.",
         properties: ["id": p("string", "Event id."),
                      "span": p("string", "For repeating events: this (default) or future.", ["enum": ["this", "future"]])],
         required: ["id"]) { a in
        let e = try findEvent(try a.need("id"))
        let j = eventJSON(e)
        try store.remove(e, span: span(a), commit: true)
        return ["deleted": j]
    },

    // Reminders
    Tool(name: "reminders_list_lists", description: "List Apple Reminders lists (id, title, account, writable, default).",
         properties: [:], required: []) { _ in
        store.calendars(for: .reminder).map { calendarJSON($0, .reminder) }
    },
    Tool(name: "reminders_list", description: "Reminders, open by default. Filter by list, text, or due before a date.",
         properties: ["list": p("string", "List title or id."), "query": p("string", "Case-insensitive text in title or notes."),
                      "due_before": p("string", "Only open reminders due before this. " + dateHint),
                      "include_completed": p("boolean", "Also completed ones (last 30 days)."),
                      "limit": p("integer", "Max results, default 100.")],
         required: []) { a in
        let cals = try a.str("list").map { [try findCalendar($0, .reminder)] }
        var items: [EKReminder]
        if let db = a.str("due_before") {
            items = fetchReminders(store.predicateForIncompleteReminders(withDueDateStarting: nil, ending: try parseDate(db).date, calendars: cals))
        } else {
            items = fetchReminders(store.predicateForIncompleteReminders(withDueDateStarting: nil, ending: nil, calendars: cals))
            if a.bool("include_completed") == true {
                items += fetchReminders(store.predicateForCompletedReminders(withCompletionDateStarting: Date().addingTimeInterval(-30 * 86400), ending: nil, calendars: cals))
            }
        }
        if let q = a.str("query") {
            items = items.filter { r in [r.title, r.notes].contains { $0?.localizedCaseInsensitiveContains(q) == true } }
        }
        func due(_ r: EKReminder) -> Date { r.dueDateComponents.flatMap { Calendar.current.date(from: $0) } ?? .distantFuture }
        items.sort { due($0) < due($1) }
        return items.prefix(a.int("limit") ?? 100).map(reminderJSON)
    },
    Tool(name: "reminders_create", description: "Create a reminder. A due date with time also sets an alert at that time, so it notifies on iPhone and Mac.",
         properties: ["title": p("string", "What to remember."), "due": p("string", dateHint),
                      "list": p("string", "List title or id; default list if omitted."), "notes": p("string", "Notes."),
                      "priority": p("integer", "0 none, 1 high, 5 medium, 9 low."), "recurrence": recurrenceProp],
         required: ["title"]) { a in
        let r = EKReminder(eventStore: store)
        r.calendar = try findCalendar(a.str("list"), .reminder)
        try applyReminder(r, a)
        try store.save(r, commit: true)
        return reminderJSON(r)
    },
    Tool(name: "reminders_update", description: "Change a reminder by id. Only given fields change; due '' removes the due date.",
         properties: ["id": p("string", "Reminder id."), "title": p("string", "Title."), "due": p("string", dateHint),
                      "list": p("string", "Move to this list."), "notes": p("string", "Notes."),
                      "priority": p("integer", "0 none, 1 high, 5 medium, 9 low."), "recurrence": recurrenceProp,
                      "completed": p("boolean", "Mark done or not done.")],
         required: ["id"]) { a in
        let r = try findReminder(try a.need("id"))
        try applyReminder(r, a)
        if let c = a.bool("completed") { r.isCompleted = c }
        try store.save(r, commit: true)
        return reminderJSON(r)
    },
    Tool(name: "reminders_complete", description: "Mark a reminder as done.",
         properties: ["id": p("string", "Reminder id.")], required: ["id"]) { a in
        let r = try findReminder(try a.need("id"))
        r.isCompleted = true
        try store.save(r, commit: true)
        return reminderJSON(r)
    },
    Tool(name: "reminders_delete", description: "Delete a reminder by id.",
         properties: ["id": p("string", "Reminder id.")], required: ["id"]) { a in
        let r = try findReminder(try a.need("id"))
        let j = reminderJSON(r)
        try store.remove(r, commit: true)
        return ["deleted": j]
    },
]

let toolsByName = Dictionary(uniqueKeysWithValues: tools.map { ($0.name, $0) })

// MARK: - MCP (JSON-RPC)

func json(_ v: Any) -> String {
    let data = (try? JSONSerialization.data(withJSONObject: v, options: [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes])) ?? Data("null".utf8)
    return String(decoding: data, as: UTF8.self)
}

func rpcResult(_ id: Any, _ result: Any) -> [String: Any] { ["jsonrpc": "2.0", "id": id, "result": result] }
func rpcError(_ id: Any, _ code: Int, _ message: String) -> [String: Any] {
    ["jsonrpc": "2.0", "id": id, "error": ["code": code, "message": message]]
}

/// Returns nil for notifications (no response body).
func handleRPC(_ msg: [String: Any]) -> [String: Any]? {
    let method = msg["method"] as? String ?? ""
    guard let id = msg["id"], !(id is NSNull) else { return nil }
    let params = msg["params"] as? [String: Any] ?? [:]
    switch method {
    case "initialize":
        return rpcResult(id, [
            "protocolVersion": params["protocolVersion"] as? String ?? "2025-06-18",
            "capabilities": ["tools": ["listChanged": false]],
            "serverInfo": ["name": "morzik-bridge", "version": "0.1.0"],
            "instructions": "The user's Apple Calendar and Reminders on his Mac. Times without an offset are the Mac's local time (\(tz.identifier)).",
        ])
    case "ping":
        return rpcResult(id, [:])
    case "tools/list":
        return rpcResult(id, ["tools": tools.map { t in
            ["name": t.name, "description": t.description,
             "inputSchema": ["type": "object", "properties": t.properties, "required": t.required]]
        }])
    case "tools/call":
        let name = params["name"] as? String ?? ""
        guard let tool = toolsByName[name] else { return rpcError(id, -32602, "unknown tool '\(name)'") }
        let args = Args(raw: params["arguments"] as? [String: Any] ?? [:])
        let type: EKEntityType = name.hasPrefix("reminders_") ? .reminder : .event
        if name != "status", EKEventStore.authorizationStatus(for: type) != .fullAccess {
            let what = type == .event ? "Calendar" : "Reminders"
            return rpcResult(id, ["content": [["type": "text", "text":
                "No access to \(what) on the Mac (\(accessStatus(type))). The user has to allow Morzik Bridge in System Settings → Privacy & Security → \(what)."]],
                "isError": true])
        }
        do {
            let value = try ekQueue.sync { try tool.handler(args) }
            return rpcResult(id, ["content": [["type": "text", "text": json(value)]], "isError": false])
        } catch let e as ToolError {
            return rpcResult(id, ["content": [["type": "text", "text": e.message]], "isError": true])
        } catch {
            return rpcResult(id, ["content": [["type": "text", "text": "\(error.localizedDescription)"]], "isError": true])
        }
    default:
        return rpcError(id, -32601, "method not found: \(method)")
    }
}

// MARK: - HTTP

struct Request {
    let method: String
    let path: String
    let headers: [String: String]
    let body: Data
}

func response(_ status: Int, _ reason: String, _ body: Data = Data(), contentType: String = "application/json") -> Data {
    var head = "HTTP/1.1 \(status) \(reason)\r\nContent-Length: \(body.count)\r\n"
    if !body.isEmpty { head += "Content-Type: \(contentType)\r\n" }
    if status == 401 { head += "WWW-Authenticate: Bearer\r\n" }
    head += "\r\n"
    return Data(head.utf8) + body
}

func route(_ req: Request) -> Data {
    let path = req.path.split(separator: "?").first.map(String.init) ?? req.path
    if req.method == "GET" && path == "/health" { return response(200, "OK", Data("{\"ok\":true}".utf8)) }
    guard path == "/mcp" else { return response(404, "Not Found") }
    guard req.headers["authorization"] == "Bearer \(token)" else { return response(401, "Unauthorized") }
    guard req.method == "POST" else { return response(405, "Method Not Allowed") }
    guard let parsed = try? JSONSerialization.jsonObject(with: req.body) else {
        return response(400, "Bad Request", Data(json(rpcError(NSNull(), -32700, "parse error")).utf8))
    }
    if let batch = parsed as? [[String: Any]] {
        let replies = batch.compactMap(handleRPC)
        return replies.isEmpty ? response(202, "Accepted") : response(200, "OK", Data(json(replies).utf8))
    }
    guard let msg = parsed as? [String: Any] else { return response(400, "Bad Request") }
    guard let reply = handleRPC(msg) else { return response(202, "Accepted") }
    return response(200, "OK", Data(json(reply).utf8))
}

final class Connection {
    let conn: NWConnection
    var buffer = Data()
    init(_ c: NWConnection) { conn = c }

    func start(on queue: DispatchQueue) {
        conn.stateUpdateHandler = { [self] state in
            if case .failed = state { conn.cancel() }
        }
        conn.start(queue: queue)
        receive()
    }

    func receive() {
        conn.receive(minimumIncompleteLength: 1, maximumLength: 1 << 20) { [self] data, _, done, err in
            if let data { buffer.append(data) }
            while let req = parse() { conn.send(content: route(req), completion: .contentProcessed { _ in }) }
            if done || err != nil || buffer.count > 8 << 20 { conn.cancel(); return }
            receive()
        }
    }

    func parse() -> Request? {
        guard let headEnd = buffer.range(of: Data("\r\n\r\n".utf8)) else { return nil }
        let head = String(decoding: buffer[buffer.startIndex..<headEnd.lowerBound], as: UTF8.self)
        var lines = head.components(separatedBy: "\r\n")
        let start = lines.removeFirst().split(separator: " ")
        guard start.count >= 2 else { conn.cancel(); return nil }
        var headers: [String: String] = [:]
        for l in lines {
            guard let i = l.firstIndex(of: ":") else { continue }
            headers[l[..<i].lowercased()] = l[l.index(after: i)...].trimmingCharacters(in: .whitespaces)
        }
        let length = Int(headers["content-length"] ?? "0") ?? 0
        let bodyStart = headEnd.upperBound
        guard buffer.count - (bodyStart - buffer.startIndex) >= length else { return nil }
        let body = buffer[bodyStart..<(bodyStart + length)]
        buffer = Data(buffer[(bodyStart + length)...])
        return Request(method: String(start[0]), path: String(start[1]), headers: headers, body: Data(body))
    }
}

// MARK: - Main

// Ask in the background: the permission dialogs wait for a click, the server shouldn't.
DispatchQueue.global().async {
    requestAccess()
    log("calendar: \(accessStatus(.event)), reminders: \(accessStatus(.reminder))")
}
NotificationCenter.default.addObserver(forName: .EKEventStoreChanged, object: store, queue: nil) { _ in
    ekQueue.async { store.refreshSourcesIfNecessary() }
}

let netQueue = DispatchQueue(label: "morzik-bridge.net")
let params = NWParameters.tcp
params.requiredLocalEndpoint = .hostPort(host: NWEndpoint.Host(host), port: NWEndpoint.Port(rawValue: port)!)
params.allowLocalEndpointReuse = true
let listener = try NWListener(using: params)
listener.newConnectionHandler = { Connection($0).start(on: netQueue) }
listener.stateUpdateHandler = { state in
    log("listener \(host):\(port): \(state)")
    if case .failed = state { exit(1) }
}
listener.start(queue: netQueue)
dispatchMain()
