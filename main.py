from dataclasses import dataclass, asdict
import datetime as dt
import json, re, time
from typing import Literal

import pandas as pd
import fitz
from pymupdf import Document

# TODOs
#   - [x] Some questions take up more than one page. Identify a mechanism to identify the page ranges of a question
#   - [ ] Fix duplications of the same questions
#   - [x] Fix parsing issue with R&W pdfs
#   - [ ] Output to both json and csv
#       - Use pandas dataframe
#   - [ ] Add repl to interact with and has the following features
#       - [ ] Filtering
#       - [ ] Question organizations (r&w hard random, math easy random, math hard 1,2,4,23)
#       - [ ] Any combination of questions

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

class Timer:
    def __init__(self) -> None:
        self._start: float = time.time()

    def start(self) -> None:
        self._start: float = time.time()

    def stop(self, msg: str) -> None:
        diff = time.time() - self._start
        if diff >= 1.0:
            diff_str = f"{diff:.3f} s"
        else:
            diff_ms = diff * 1000
            diff_str = f"{diff_ms:.3f} ms"

        print(f"[{diff_str:>10}] {msg}")


def pdf_output_path_name(subject: str, difficulty: str, excluded: bool) -> str:
    excluded_str = "excluded" if excluded else ""

    return f"{subject}-{excluded_str}-{difficulty}"


pdf_paths: dict[str, dict] = {
    "all-math-excluded-easy.pdf": {
        "subject": "Math",
        "difficulty": "easy",
        "excluded": True,
    },
    "all-math-excluded-medium.pdf": {
        "subject": "Math",
        "difficulty": "medium",
        "excluded": True,
    },
    "all-math-excluded-hard.pdf": {
        "subject": "Math",
        "difficulty": "hard",
        "excluded": True,
    },
    "all-rw-excluded-easy.pdf": {
        "subject": "R&W",
        "difficulty": "easy",
        "excluded": True,
    },
    "all-rw-excluded-medium.pdf": {
        "subject": "R&W",
        "difficulty": "medium",
        "excluded": True,
    },
    "all-rw-excluded-hard.pdf": {
        "subject": "R&W",
        "difficulty": "hard",
        "excluded": True,
    },
}

@dataclass
class SSQBInfo:
    q_id: str
    domain: str
    skill: str
    page_nos: str

timer: Timer = Timer()


def process_question_pdf(path: str, output_path_name: str, format: Literal['csv', 'json']) -> None:
    global timer

    print(f"Working on {path}...")

    doc: Document = fitz.open(path)
    last_page_no: int = 0
    q_infos: list[SSQBInfo] = []

    timer.start()
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)

        text = page.get_text()
        assert isinstance(text, str)

        id: int = text.find("ID: ")
        labels: int = text.find("Assessment")

        q_id_pat = r"ID: ([0-9a-f]*)"
        matches = re.findall(q_id_pat, text[id:labels])
        if len(matches) != 1:
            # This probably means that one question takes up multiple pages
            # print(f"No ID found in page {page_num + 1}")
            continue
        else:
            last_page_no = page_num

        if page_num - last_page_no >= 1:
            page_num_str = ""
            for num in range(last_page_no, page_num+1):
                page_num_str += str(num + 1)
        else:
            page_num_str = str(page_num + 1)

        q_id = matches[0]

        label_infos = ' '.join(text[labels:].split())
        label_info_pat = r"Assessment (\w*) Test ([\w\s]*) Domain ([\w\s]*) Skill ([\w\s]*) D"
        matches = re.findall(label_info_pat, label_infos)
        for mat in matches:
            assessment, test, domain, skill = mat
            assert assessment == "SAT"
            q_infos.append(SSQBInfo(
                q_id,
                domain,
                skill,
                page_num_str
            ))

    timer.stop(f"Completed parsing '{path}'")

    timer.start()
    q_dicts = []
    data: dict = {
        "ID": [],
        "Pages": [],
        "Domain": [],
        "Skill": [],
    }
    for info in q_infos:
        data["ID"].append(info.q_id)
        data["Pages"].append(info.page_nos)
        data["Domain"].append(info.domain)
        data["Skill"].append(info.skill)

    df: pd.DataFrame = pd.DataFrame(data)
    output_path = f"{output_path_name.lower()}.{format}"
    if format == "csv":
        df.to_csv(output_path, index=False)
    elif format == "json":
        df.to_json(output_path, index=False)
    else:
        print(f"Failed to export: Unknown format ('{format}')")
        print("Exporting to csv...")
        df.to_csv(output_path, index=False)

    timer.stop(f"Completed exporting '{path}'\n-------------")


meta_info_list: list[dict] = []
for pdf_path, info in pdf_paths.items():
    subject = info["subject"]
    difficulty = info["difficulty"]
    assert subject in ["Math", "R&W"], f"Subject('{subject}') must be either Math or R&W."
    assert difficulty in ["easy", "medium", "hard"], (
        f"Difficulty('{difficulty}') must be easy, medium, or hard"
    )

    meta_info_list.append({
        "parsed_at": str(dt.datetime.now()),
        "source_pdf": pdf_path,
        "subject": subject,
        "difficulty": difficulty,
        "excluded": info["excluded"],
    })

    output_name = pdf_output_path_name(**info)
    process_question_pdf(pdf_path, output_name, "csv")

with open("meta_infos.json", "w") as f:
    json.dump(meta_info_list, f, indent=4)
