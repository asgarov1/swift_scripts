#!/usr/bin/env python3
"""Repair known machine-translation errors in the generated Swedish A1 JSON."""

from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


FILES = ("vocabulary.json", "phrases.json", "verbs.json", "grammar.json")

PRONOUN_I = {
    "en": "I",
    "zh-Hans": "我",
    "hi": "मैं",
    "es": "yo",
    "ar": "أنا",
    "fr": "je",
    "bn": "আমি",
    "pt": "eu",
    "ru": "я",
    "ur": "میں",
    "id": "saya",
    "de": "ich",
    "ja": "私",
    "sw": "mimi",
    "mr": "मी",
    "te": "నేను",
    "tr": "ben",
    "ta": "நான்",
    "yue-Hant": "我",
    "vi": "tôi",
    "sh": "ja",
    "hu": "én",
    "pl": "ja",
    "bg": "аз",
}

KNOWN_REPLACEMENTS = {
    ("vocabulary.json", "Varm", "pt"): "Quente",
    ("vocabulary.json", "Nej", "yue-Hant"): "唔係",
    ("vocabulary.json", "Äpple", "sw"): "Tufaha",
    ("verbs.json", "kunna", "bn"): "সক্ষম হওয়া, পারা",
    ("verbs.json", "kunna", "es"): "poder",
    ("verbs.json", "kunna", "zh-Hans"): "能够，会",
    ("verbs.json", "kunna", "de"): "können",
    ("verbs.json", "kunna", "ja"): "できる",
    ("verbs.json", "kunna", "sw"): "kuweza",
    ("verbs.json", "kunna", "te"): "చేయగలగడం",
    ("verbs.json", "kunna", "tr"): "yapabilmek",
    ("verbs.json", "kunna", "ta"): "முடிதல்",
    ("verbs.json", "kunna", "yue-Hant"): "能夠，可以",
    ("verbs.json", "kunna", "vi"): "có thể",
    ("verbs.json", "kunna", "pl"): "móc",
    ("verbs.json", "kunna", "bg"): "мога",
    ("verbs.json", "måste", "bn"): "অবশ্যই করতে হবে",
    ("verbs.json", "vara", "yue-Hant"): "係",
    ("verbs.json", "måste", "yue-Hant"): "必須，要",
}

ARTICLE_SOURCES = {
    "En": "indefinite article used with Swedish common-gender nouns",
    "Ett": "indefinite article used with Swedish neuter-gender nouns",
}


def translate(text: str, target: str, retries: int = 4) -> str:
    params = urllib.parse.urlencode(
        {"client": "gtx", "sl": "en", "tl": target, "dt": "t", "q": text}
    )
    url = f"https://translate.googleapis.com/translate_a/single?{params}"
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8"))
            result = "".join(part[0] for part in payload[0] if part and part[0]).strip()
            if not result:
                raise RuntimeError("empty translation")
            time.sleep(0.06)
            return result
        except Exception as exc:
            last_error = exc
            print(
                f"ERROR {text!r} -> {target}, attempt {attempt + 1}/{retries}: {exc}"
            )
            time.sleep(0.6 * (attempt + 1))
    raise RuntimeError(f"translation failed: {text!r} -> {target}: {last_error}")


def localization_maps(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"translations", "titles", "explanations"} and isinstance(
                child, dict
            ):
                yield child
            yield from localization_maps(child)
    elif isinstance(value, list):
        for child in value:
            yield from localization_maps(child)


def write_json_atomic(path: Path, data: Any) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def apply_deterministic_repairs(loaded: dict[str, Any]) -> None:
    vocabulary = loaded["vocabulary.json"]
    jag = next(item for item in vocabulary if item.get("foreign") == "Jag")
    jag["translations"].update(PRONOUN_I)

    for (filename, identifier, locale), replacement in KNOWN_REPLACEMENTS.items():
        key = "foreign" if filename == "vocabulary.json" else "infinitive"
        item = next(entry for entry in loaded[filename] if entry.get(key) == identifier)
        item["translations"][locale] = replacement

    grammar = loaded["grammar.json"]
    rules_by_title = {rule["titles"]["en"]: rule for rule in grammar}

    rules_by_title["Negation with inte"]["explanations"].update(
        {
            "bn": "একটি বাক্য নেতিবাচক করতে inte ব্যবহার করুন। একটি সাধারণ প্রধান বাক্যে, inte সাধারণত রূপান্তরিত ক্রিয়ার পরে আসে।",
            "ur": "کسی جملے کو منفی بنانے کے لیے inte استعمال کریں۔ ایک سادہ مرکزی جملے میں، inte عام طور پر صرف شدہ فعل کے بعد آتا ہے۔",
            "mr": "वाक्य नकारात्मक करण्यासाठी inte वापरा. साध्या मुख्य वाक्यात inte सहसा रूपांतरित क्रियापदानंतर येते.",
        }
    )
    rules_by_title["En and Ett Nouns"]["titles"]["ur"] = "En اور Ett اسم"
    rules_by_title["En and Ett Nouns"]["explanations"].update(
        {
            "bn": "সুইডিশ বিশেষ্যগুলির দুটি লিঙ্গ রয়েছে: en সহ সাধারণ লিঙ্গ এবং ett সহ নপুংসক লিঙ্গ। প্রতিটি বিশেষ্য তার নিবন্ধের সাথে একসাথে শিখুন।",
            "ur": "سویڈش اسم کی دو جنسیں ہوتی ہیں: en کے ساتھ عام جنس اور ett کے ساتھ غیر جانبدار جنس۔ ہر اسم کو اس کے مضمون کے ساتھ سیکھیں۔",
            "sw": "Nomino za Kiswidi zina jinsia mbili: jinsia ya kawaida yenye en na jinsia isiyo na upande yenye ett. Jifunze kila nomino pamoja na makala yake.",
            "mr": "स्वीडिश संज्ञांना दोन लिंगे असतात: en सह सामान्य लिंग आणि ett सह नपुंसकलिंगी. प्रत्येक संज्ञा तिच्या लेखासह शिका.",
            "ta": "ஸ்வீடிஷ் பெயர்ச்சொற்களுக்கு இரண்டு பாலினங்கள் உள்ளன: en உடன் பொதுப் பாலினம் மற்றும் ett உடன் நடுநிலைப் பாலினம். ஒவ்வொரு பெயர்ச்சொல்லையும் அதன் உருபுடன் சேர்த்து கற்கவும்.",
        }
    )
    definite = rules_by_title["Definite Nouns"]
    definite["explanations"].update(
        {
            "bn": "সুইডিশ ভাষায় প্রায়ই বিশেষ্যের শেষে নির্দিষ্ট নিবন্ধ যোগ করা হয়। En বিশেষ্যগুলি সাধারণত -en যোগ করে, আর ett বিশেষ্যগুলি সাধারণত -et যোগ করে।",
            "ur": "سویڈش میں اکثر اسم کے آخر میں معرفہ مضمون شامل کیا جاتا ہے۔ En اسم عام طور پر -en لیتے ہیں، اور ett اسم عام طور پر -et لیتے ہیں۔",
            "mr": "स्वीडिशमध्ये अनेकदा संज्ञेच्या शेवटी निश्चित लेख जोडला जातो. En संज्ञांना सामान्यतः -en लागते, आणि ett संज्ञांना सामान्यतः -et लागते.",
        }
    )
    boken = next(example for example in definite["examples"] if example["foreign"] == "boken")
    boken["translations"]["es"] = "el libro"
    boken["translations"]["pl"] = "książka"

    rules_by_title["Modal Verbs"]["explanations"].update(
        {
            "ur": "عام موڈل فعل میں kan، vill، måste، اور ska شامل ہیں۔ اگلا فعل مصدر کی شکل میں رہتا ہے۔",
            "mr": "सामान्य मोडल क्रियापदांमध्ये kan, vill, måste आणि ska यांचा समावेश होतो. पुढील क्रियापद infinitive रूपात राहते.",
            "yue-Hant": "常見嘅情態動詞包括 kan、vill、måste 同 ska。下一個動詞保持喺不定式形式。",
        }
    )
    rules_by_title["Adjectives"]["explanations"].update(
        {
            "ur": "بنیادی سویڈش صفتیں اسم کے ساتھ بدل سکتی ہیں۔ بہت سی صفتیں ett اسم کے ساتھ -t اور جمع اسم کے ساتھ -a کا اضافہ کرتی ہیں۔",
            "mr": "मूलभूत स्वीडिश विशेषणे संज्ञेनुसार बदलू शकतात. अनेक विशेषणांना ett संज्ञांसह -t आणि अनेकवचनी संज्ञांसह -a जोडले जाते.",
        }
    )
    possessive = rules_by_title["Possessive Pronouns"]
    possessive["explanations"].update(
        {
            "ur": "min، din، hans، hennes، vår، اور er جیسے ملکیتی ضمیر ملکیت ظاہر کرتے ہیں۔ Min اور din، ett اسم کے ساتھ mitt اور ditt بن جاتے ہیں۔",
            "mr": "min, din, hans, hennes, vår आणि er यांसारखी स्वामित्वदर्शक सर्वनामे मालकी दाखवतात. Min आणि din ett संज्ञांसह mitt आणि ditt होतात.",
            "yue-Hant": "所有格，例如 min、din、hans、hennes、vår 同 er，都係表示擁有權。Min 同 din 用 ett 名詞時變成 mitt 同 ditt。",
        }
    )
    mitt_hus = next(example for example in possessive["examples"] if example["foreign"] == "mitt hus")
    mitt_hus["translations"]["hi"] = "मेरा घर"

    rules_by_title["The Infinitive and att"]["titles"].update(
        {
            "ur": "مصدر اور att",
            "mr": "Infinitive आणि att",
            "ta": "வினையெச்சம் மற்றும் att",
        }
    )
    rules_by_title["Object Pronouns"]["explanations"][
        "ta"
    ] = "பொருள் பிரதிபெயர்கள் ஒரு செயலைப் பெறும் நபர் அல்லது பொருளை மாற்றுகின்றன. பொதுவான வடிவங்கள் mig, dig, honom, henne, den, det, oss, er மற்றும் dem."
    rules_by_title["Prepositions of Place"]["explanations"][
        "yue-Hant"
    ] = "常見嘅地方介詞包括 i（喺入面）、på（喺上面或者喺）、under（喺下面）、över（喺上面）、framför（喺前面）同 bredvid（喺旁邊）。"
    help_phrase = next(
        phrase for phrase in loaded["phrases.json"] if phrase.get("foreign") == "Hjälp!"
    )
    help_phrase["translations"]["yue-Hant"] = "救命！"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("--deterministic-only", action="store_true")
    args = parser.parse_args()

    loaded = {}
    file_maps = {}
    for filename in FILES:
        loaded[filename] = json.loads(
            (args.folder / filename).read_text(encoding="utf-8")
        )
        file_maps[filename] = list(localization_maps(loaded[filename]))

    if not args.deterministic_only:
        total_maps = sum(len(maps) for maps in file_maps.values())
        current = 0
        for filename, maps in file_maps.items():
            for mapping in maps:
                current += 1
                mapping["yue-Hant"] = translate(mapping["en"], "yue")
                print(
                    f"[{current}/{total_maps}] Cantonese: "
                    f"{mapping['en']!r} -> {mapping['yue-Hant']!r}"
                )
            write_json_atomic(args.folder / filename, loaded[filename])
            print(f"checkpointed {args.folder / filename}")

        vocabulary = loaded["vocabulary.json"]
        locale_codes = {
            locale: ("zh-CN" if locale == "zh-Hans" else "yue" if locale == "yue-Hant" else "hr" if locale == "sh" else locale)
            for locale in PRONOUN_I
            if locale != "en"
        }
        for foreign, source in ARTICLE_SOURCES.items():
            item = next(
                entry
                for entry in vocabulary
                if entry.get("foreign") == foreign
                and str(entry.get("translations", {}).get("en", "")).startswith("A/an")
            )
            for locale, code in locale_codes.items():
                item["translations"][locale] = translate(source, code)

    apply_deterministic_repairs(loaded)

    for filename, data in loaded.items():
        write_json_atomic(args.folder / filename, data)
        print(f"updated {args.folder / filename}")


if __name__ == "__main__":
    main()
