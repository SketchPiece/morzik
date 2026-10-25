"""Ask the real Jev about made-up messages and compare with the expected route.

Run on the server as morzik (needs MORZIK_ROUTER_OPENROUTER_KEY in ~/.hermes/.env):
    python3 -I router/bench.py
The messages are invented, in the shape of what Morzik gets; never put real ones here.
"""

import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import classify  # noqa: E402

L, H = classify.LIGHT, classify.HEAVY

# (message, previous turn tool calls or the assistant's last reply, expected)
CASES = [
    ("Привет", 0, L), ("Ты тут?", 0, L), ("Что умеешь?", 0, L), ("Шо делаешь", 0, L),
    ("Помурлыкай мне :3", 0, L), ("Спасибо, бро", 0, L), ("Ок", 0, L), ("Как оно быть котом?", 0, L),
    ("Когда построили Эйфелеву башню?", 0, L), ("Есть что на почте?", 0, L),
    ("Пометь их прочитанными", 1, L), ("Напомни завтра в 9 позвонить в сервис", 0, L),
    ("Что у меня завтра в календаре?", 0, L), ("Какая погода в Варшаве на выходных?", 0, L),
    ("Запиши голосовое, как ты мурлыкаешь", 0, L), ("Называй меня босс, но только в шутку", 0, L),
    ("[Кнопка /start: просто поздоровайся одной фразой]", 0, L), ("Переведи: Reserva confirmada", 0, L),
    ("Зайди на сайт банка и достань последнюю выписку", 0, H), ("Сделай драфт ответа арендодателю", 0, H),
    ("Сравни эти два варианта жилья и посоветуй", 0, H), ("Почини флуд бота с бэкапами", 0, H),
    ("Оплати счёт за домен", 0, H), ("Поменяй жильё в плане поездки на это", 0, H),
    ("Что тут?  [Image attached at: /tmp/photo.png]", 0, H),
    ("[The user sent a document: 'booking.pdf'. It is saved at: /tmp/booking.pdf]", 0, H),
    ("А эта норм? https://example.com/rooms/123", 0, H), ("Удали все напоминания из списка Работа", 0, H),
    ("Найди в переписке анкету и проверь, где это было написано", 0, H),
    ("Давай ещё раз", 6, H), ("Да", 5, H), ("Давай ещё раз", 0, L), ("Да", 0, L),
    ("Подключи мне новый почтовый ящик", 0, H),
    # the same short answer means different things after different questions
    ("Да", "Нашёл письмо от арендодателя. Набросать ответ?", H),
    ("Да, давай", "Оплатить счёт картой, которая привязана?", H),
    ("Второй", "Вот два варианта жилья на даты поездки. Какой берём в план?", H),
    ("Да", "Хочешь, расскажу, почему коты спят по 16 часов?", L),
    ("Ага", "Поставить напоминание на завтра на 9 утра?", L),
    ("Найс", "Готово, бронь подтверждена.", L),
]


def main():
    key = classify._key()
    if not key:
        sys.exit(f"no {classify.KEY_ENV}")
    rows, times = [], []
    for text, before, expected in CASES:
        if isinstance(before, str):
            history = [{"role": "user", "content": "привет"}, {"role": "assistant", "content": before}]
        else:
            history = [{"role": "user", "content": "x"}] + [
                {"role": "assistant", "tool_calls": [{"name": "browser_exec"}]}] * before
        started = time.monotonic()
        route, reason, confidence = classify.classify(text, history, key=key)
        times.append(time.monotonic() - started)
        rows.append((route == expected, route, expected, reason, confidence, text))
    for ok, route, expected, reason, confidence, text in rows:
        print(f"{'  ' if ok else '✗ '}{route:5} (want {expected:5}) {reason:7} {confidence:.2f}  {text[:60]}")
    wrong_light = sum(1 for ok, route, *_ in rows if not ok and route == L)
    wrong_heavy = sum(1 for ok, route, *_ in rows if not ok and route == H)
    print(f"\n{sum(r[0] for r in rows)}/{len(rows)} right; light by mistake: {wrong_light}, "
          f"heavy by mistake: {wrong_heavy}; latency median {statistics.median(times):.2f}s, max {max(times):.2f}s")


if __name__ == "__main__":
    main()
