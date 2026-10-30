"""Editorial regressions, not an automatic proof that every term is explained.

Teach a necessary new term at its first substantive use, in ordinary language.
Keep a short explanation at the point of reading, inline or in an accessible card.
A later chapter, a glossary alone or a source caption is not a replacement.
This file checks the inline source fallback; test_terms_ui.js checks the cards.
Titles/route previews may name forthcoming topics; code is not explanatory prose.
Read diagrams in place and respect station 6's explicit reading order.
"""
import html
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


def plain(value):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", value))).strip()


def fragments(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"lead", "html"} and isinstance(item, str):
                if not re.search(r"Основание и границы|[Пп]ервоисточник|[Ии]сточники|Первичные источники", item):
                    yield plain(item)
            elif isinstance(item, (dict, list)) and key not in {"sources", "quizzes", "tasks"}:
                yield from fragments(item)
    elif isinstance(value, list):
        for item in value:
            yield from fragments(item)


def teaching_blocks(station):
    sections = station["theory"]
    if station.get("readingOrder"):
        by_id = {s["id"]: s for s in sections}
        sections = [by_id[sid] for sid in station["readingOrder"]]
    for section in sections:
        if section["id"] != "learning-route":
            yield from fragments(section)


class Terminology(unittest.TestCase):
    def test_selected_first_uses_have_nearby_explanations(self):
        # Each marker must be in the first paragraph that teaches the term,
        # rather than merely somewhere in a 20–90-section station.
        cases = [
            (0, r"инвариант\w*", "условие"),
            (1, r"\bRAII\b", "деструкторе"),
            (1, r"\bAPI\b", "программный интерфейс"),
            (2, r"\bABI\b", "двоичных соглашений"),
            (3, r"\bSTL\b", "контейнеры"),
            (3, r"\bSSO\b", "короткой строки"),
            (3, r"\bFIFO\b", "первым пришёл"),
            (3, r"\bRSS\b", "оперативной памяти"),
            (5, r"\bCMake\b", "правила его сборки"),
            (5, r"\bJSON\b", "представления структурированных данных"),
            (5, r"\bCI\b", "непрерывная интеграция"),
            (6, r"\bhappens-before\b", "связь порядка"),
            (6, r"\bmutex\b", "мьютекс"),
            (6, r"\bABA\b", "сменилось на B"),
            (7, r"\bTCP\b", "потока байтов"),
            (7, r"\bUDP\b", "датаграммами"),
            (7, r"\bDNS\b", "система доменных имён"),
            (7, r"\bNAT\b", "преобразовании IP-адресов"),
            (7, r"\bFCS\b", "контрольная сумма кадра"),
            (8, r"\bREST\b", "архитектурный стиль"),
            (8, r"\bRPC\b", "удалённом вызове"),
            ("9-sql", r"\bСУБД\b", "система управления базами данных"),
            (10, r"\bTDD\b", "разработке через тестирование"),
            (1, r"\baliasing\b", "не обязательно указывает"),
            (2, r"\bvtable\b", "таблицу адресов"),
            (3, r"инвалидац\w*", "пригодности"),
            (3, r"\bsentinels?\b", "объектом-границей"),
            (4, r"предуслови\w*", "требования"),
            (5, r"артефакт\w*", "сохраняемых результатов"),
            (6, r"\bMESI\b", "протоколов согласования"),
            (7, r"\bbacklog\b", "предел очереди"),
            (7, r"\bstrand\b", "не допускающий одновременного"),
            (8, r"\bJWT\b", "формат передачи утверждений"),
            (8, r"\bCORS\b", "браузер уточняет"),
            ("9-sql", r"\bCTE\b", "именованный результат"),
            ("9-sql", r"\bUPSERT\b", "конфликте уникального ключа"),
            (9, r"\bB-tree\b", "сбалансированное дерево"),
            (10, r"\bdigest\b", "идентификатор его конкретного содержимого"),
        ]
        for number, term, explanation in cases:
            with self.subTest(station=number, term=term):
                station = json.loads((ROOT / f"content/station{number}.json").read_text())
                first = next((p for p in teaching_blocks(station) if re.search(term, p, re.I)), None)
                self.assertIsNotNone(first, term)
                self.assertIn(explanation, first)

    def test_invariant_is_explained_in_the_reported_sentence(self):
        station = json.loads((ROOT / "content/station0.json").read_text())
        paragraph = next(p for p in teaching_blocks(station) if re.search(r"инвариант\w*", p, re.I))
        self.assertIn("условие", paragraph)
        self.assertRegex(paragraph, r"допустим(?:ое состояние|ого состояния)")
        # Both ordinary words and a code expression may explain this rule.
        # Require the concrete nonnegative-attempts example, not just a label.
        self.assertRegex(paragraph, r"остаток не должен быть отрицательным|remaining_\s*>=\s*0")

    def test_plain_english_mix_is_removed_from_known_problem_passages(self):
        station = json.loads((ROOT / "content/station7.json").read_text())
        text = " ".join(teaching_blocks(station))
        self.assertNotIn("hop LB→backend", text)
        self.assertNotIn("результат workload-dependent", text)
        cheat = json.loads((ROOT / "content/cheatsheet.json").read_text())
        prose = " ".join(item.get("rule", "") for group in cheat["stations"]
                         for section in group["sections"] for item in section["items"])
        self.assertNotIn("cleanup был привязан к lifetime", prose)
        self.assertIn("Инвариант (условие допустимого состояния объекта)", prose)

    def test_no_word_suffix_is_separated_by_an_inserted_definition(self):
        for file in (ROOT / "content").glob("station*.json"):
            station = json.loads(file.read_text())
            with self.subTest(file=file.name):
                for paragraph in teaching_blocks(station):
                    self.assertIsNone(re.search(r"\)[а-яё]+", paragraph))


if __name__ == "__main__":
    unittest.main()
