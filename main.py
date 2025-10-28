from dataclasses import dataclass, asdict
import datetime as dt
import json, re, time
from typing import Literal

import fitz

# TODOs
#   - [ ] Some questions take up more than one page. Identify a mechanism to identify the page ranges of a question

# Code used to select all checkboxes
# ======================================================
# for (let i = 0; i < 16; i++) {
#     document
#         .getElementById("results-table")
#         .querySelectorAll('input[type="checkbox"]')
#         .forEach(checkbox => {
#             checkbox.checked = true; // Check the checkbox
#             checkbox.click(); // Simulate a click event
#         });
#     setTimeout(() => console.log("waiting..."), 15000);
#     document.getElementById("undefined_next").click();
# }

Level = Literal["easy","medium", "hard"]

@dataclass
class SSQBInfo:
    q_id: str
    assessment: Literal['SAT']
    test: str
    domain: str
    skill: str
    difficulty: Level
    page_no: int


def identify_difficulty(filepath: str) -> Level | None:
    is_easy = filepath.find(filepath, "easy") >= 0
    is_medium = filepath.find(filepath, "medium") >= 0
    is_hard = filepath.find(filepath, "hard") >= 0

    assert is_easy + is_medium + is_hard == 2,
        "The file name should have exactly one difficulty metric (easy, medium, hard)"

    if is_easy: return "easy"
    if is_medium: return "medium"
    if is_hard: return "hard"

    return

meta_info = {
    "parsed_at": str(dt.datetime.now()),
    "source_pdf": pdf_path,
    "difficulty": difficulty,
}

doc = fitz.open(pdf_path)
q_infos: list[SSQBInfo] = []
start = time.time()

for page_num in range(len(doc)):
    page = doc.load_page(page_num)

    text = page.get_text()

    id: int = text.find("ID: ")
    labels: int = text.find("Assessment")

    q_id_pat = r"ID: ([0-9a-f]*)"
    matches = re.findall(q_id_pat, text[id:labels])
    assert len(matches) == 1
    q_id = matches[0]

    # print("------\n" + text[id:])

    label_infos = ' '.join(text[labels:].split())

    label_info_pat = r"Assessment (\w*) Test (\w*) Domain (\w*) Skill ([\w\s]*) D"
    matches = re.findall(label_info_pat, label_infos)
    for mat in matches:
        assessment, test, domain, skill = mat
        assert assessment == "SAT"
        assert difficulty in ["easy", "medium", "hard"]
        q_infos.append(SSQBInfo(
            q_id,
            assessment,
            test,
            domain,
            skill,
            difficulty,
            page_num
        ))

diff_ms = (time.time() - start) * 1000
print(f"Completed parsing in {diff_ms} ms")

start = time.time()

q_dicts = []
for q_i in q_infos:
    q_dicts.append(asdict(q_i))

with open(f"{difficulty}-search-info.json", "w") as f:
    json.dump({
        "meta_info": meta_info,
        "questions": q_dicts
    }, f, indent=4)

diff_ms = (time.time() - start) * 1000
print(f"Completed exporting in {diff_ms} ms")
