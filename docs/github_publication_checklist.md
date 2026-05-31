# GitHub Publication Checklist

Use this before making the StickWords repository public.

## Safe To Publish

- `README.md`
- `LICENSE`
- `app.py`
- `src/`
- `scripts/`
- `firmware/src/`
- `firmware/platformio.ini`
- `firmware/partitions.csv`
- `firmware/include/lv_conf.h`
- `firmware/include/secrets.example.h`
- `tests/`
- `docs/`, after private addresses have been generalized

## Must Stay Private

- `firmware/include/secrets.h`
- `data/*.csv`
- `.env` and `.env.*`
- any real `DEEPSEEK_API_KEY`
- any real Wi-Fi SSID/password
- screenshots that show personal vocabulary, API keys, home network names, or browser profile details

## Current Audit Result

- `firmware/include/secrets.h` is ignored by `.gitignore`.
- `data/*.csv` is ignored by `.gitignore`.
- `firmware/include/secrets.example.h` contains placeholders only.
- The tracked docs were sanitized to use generic private LAN examples such as `192.168.x.x`.
- The PC admin page may show a LAN URL such as `http://192.168.x.x:8000`. This is expected and useful for setup. It is not usually reachable from the public internet, but exact local addresses are still unnecessary in public docs or screenshots.
- The setup portal currently uses plain HTTP and has no password. Document it as a local trusted-network setup tool, not an internet-facing service.

## Pre-Push Commands

```powershell
git status --short
git ls-files firmware/include/secrets.h data/vocab.csv
git check-ignore -v firmware/include/secrets.h data/vocab.csv
rg -n "(api[_-]?key|password|secret|token|192\.168\.5\.|DEEPSEEK_API_KEY=)" . --glob "!firmware/.pio/**"
```

Expected:

- `git status --short` should contain only intentional changes.
- `git ls-files firmware/include/secrets.h data/vocab.csv` should print nothing.
- `git check-ignore` should show `.gitignore` rules for those private files.
- `rg` should not reveal real keys, real passwords, or exact private addresses from your own network.

## Suggested First GitHub Tasks

1. Create the GitHub repository.
2. Push the current branch.
3. Add screenshots after checking they do not reveal personal data.
4. Open the README on GitHub and verify the bilingual formatting.
5. Add repository topics such as `m5stick-c-plus`, `platformio`, `lvgl`, `spaced-repetition`, and `vocabulary`.
