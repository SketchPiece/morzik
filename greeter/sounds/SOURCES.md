# Звуки экрана входа (кроме мяуканья, оно в `meows/`)

Записи с Wikimedia Commons, обе свободные, атрибуция не обязательна.

| Файл | Запись | Автор | Лицензия |
|---|---|---|---|
| `purr.wav` | [Whiskers' purr edit.ogg](https://commons.wikimedia.org/wiki/File:Whiskers%27_purr_edit.ogg) | Adam Cuerden | Public domain |
| `hiss.wav` | [Cat hissing - Zabuhailo.wav](https://commons.wikimedia.org/wiki/File:Cat_hissing_-_Zabuhailo.wav) | Zabuhailo | CC0 |

Как переведены в 44,1 кГц моно для aplay:

```sh
ffmpeg -i "Whiskers' purr edit.ogg" -af "highpass=f=40,afade=t=in:d=0.3,afade=t=out:st=9.1:d=0.4,loudnorm=I=-20:TP=-2:LRA=11" -ac 1 -ar 44100 -sample_fmt s16 purr.wav
ffmpeg -i "Cat hissing - Zabuhailo.wav" -af "afade=t=in:d=0.02,afade=t=out:st=2.0:d=0.3,highpass=f=200,loudnorm=I=-16:TP=-1.5:LRA=11" -ac 1 -ar 44100 -sample_fmt s16 hiss.wav
```
