from dataclasses import dataclass, asdict
import datetime as dt
import json, re, time
from typing import Literal

import pandas as pd
import fitz
from pymupdf import Document, Page

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


def pdf_parsed_output_name(subject: str, difficulty: str, excluded: bool) -> str:
    excluded_str = "excluded" if excluded else ""

    return f"{subject}-{excluded_str}-{difficulty}"

def dedup_pdf_output_path(orig_pdf_path: str) -> str:
    return f"./dedup/dedup-{'-'.join(orig_pdf_path.split('-')[1:])}"

ORIG_PDF_PATHS: dict[str, dict] = {
    "./original/orig-math-excluded-easy.pdf": {
        "subject": "Math",
        "difficulty": "easy",
        "excluded": True,
    },
    "./original/orig-math-excluded-medium.pdf": {
        "subject": "Math",
        "difficulty": "medium",
        "excluded": True,
    },
    "./original/orig-math-excluded-hard.pdf": {
        "subject": "Math",
        "difficulty": "hard",
        "excluded": True,
    },
    "./original/orig-rw-excluded-easy.pdf": {
        "subject": "R&W",
        "difficulty": "easy",
        "excluded": True,
    },
    "./original/orig-rw-excluded-medium.pdf": {
        "subject": "R&W",
        "difficulty": "medium",
        "excluded": True,
    },
    "./original/orig-rw-excluded-hard.pdf": {
        "subject": "R&W",
        "difficulty": "hard",
        "excluded": True,
    },
}

timer: Timer = Timer()
PAGE_DELIMITER: str = ":"

@dataclass
class SSQBInfo:
    q_id: str
    domain: str
    skill: str
    page_inds: list[int]

    def pages_as_str(self) -> str:
        if len(self.page_inds) == 1:
            return str(self.page_inds[0] + 1)
        elif len(self.page_inds) == 2:
            return f"{self.page_inds[0] + 1}{PAGE_DELIMITER}{self.page_inds[1] + 1}"
        else:
            assert False, f"The page range should be a single number or formatted as '<START>{PAGE_DELIMITER}<END>'"

    def __eq__(self, other) -> bool:
        # NOTE: Equality will be detected based on the ids; therefore this function
        #       assumes that each question has a UNIQUE id
        return isinstance(other, SSQBInfo) and self.q_id == other.q_id

    def __hash__(self) -> int:
        return hash((self.q_id, self.domain, self.skill, self.page_inds[0]))

def is_page_empty(page: Page) -> bool:
    page_text = page.get_text()
    assert isinstance(page_text, str)

    has_text = bool(page_text.strip())
    has_images = bool(page.get_images())
    # has_drawings = bool(page.get_drawings())

    return not (bool(has_text) or bool(has_images))

def parse_ssqb_pdfs(path: str) -> list[SSQBInfo]:
    doc: Document = fitz.open(path)
    last_page_no: int = 0
    q_infos: list[SSQBInfo] = []

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        if is_page_empty(page):
            # Skip pages that are empty
            continue

        text = page.get_text()
        assert isinstance(text, str)

        id: int = text.find("ID: ")
        labels: int = text.find("Assessment")

        q_id_pat = r"ID: ([0-9a-f]+)"
        matches = re.findall(q_id_pat, text[id:labels])
        if len(matches) != 1:
            # This probably means that one question takes up multiple pages
            # print(f"No ID found in page {page_num + 1}")
            continue

        page_inds: list[int] = []
        if page_num - last_page_no > 1:
            page_inds = [last_page_no + 1, page_num]
        else:
            page_inds = [page_num]

        last_page_no = page_num
        q_id: str = matches[0]

        label_infos = ' '.join(text[labels:].split())
        label_info_pat = r"Assessment (\w*) Test ([\w\s]*) Domain ([\w\s]*) Skill ([\w\s]*) D"
        matches = re.findall(label_info_pat, label_infos)
        for mat in matches:
            assessment, _, domain, skill = mat
            assert assessment == "SAT"
            q_infos.append(SSQBInfo(
                q_id,
                domain,
                skill,
                page_inds
            ))

    return q_infos

def ssqb_infos_to_df(ssqb_infos: list[SSQBInfo]) -> pd.DataFrame:
    # Convert to dataframe
    data: dict = {
        "ID": [],
        "Pages": [],
        "Domain": [],
        "Skill": [],
    }
    for info in ssqb_infos:
        data["ID"].append(info.q_id)
        data["Pages"].append(info.pages_as_str())
        data["Domain"].append(info.domain)
        data["Skill"].append(info.skill)

    return pd.DataFrame(data)

def dedup_ssqb_pdfs(pdf_path: str) -> Document:
    ssqb_infos: list[SSQBInfo] = parse_ssqb_pdfs(pdf_path)
    assert len(ssqb_infos) > 0, "Parsed ssqb info should have some objects in it."

    dedup_ssqb: list[SSQBInfo] = []
    for ssqb in ssqb_infos:
        if ssqb not in dedup_ssqb:
            dedup_ssqb.append(ssqb)

    orig_doc: Document = fitz.open(pdf_path)
    dedup_doc: Document = Document()

    for ssqb in dedup_ssqb:
        page_nos: list[int] = ssqb.page_inds
        if len(page_nos) == 1:
            page_nos.append(page_nos[0])

        assert len(page_nos) == 2, f"A page range should have only 2 numbers -> pages: {page_nos}"

        for pg_no in range(page_nos[0], page_nos[1] + 1):
            if not is_page_empty(orig_doc.load_page(pg_no)):
            # if not is_page_empty(orig_doc.load_page(pg_no)):
                dedup_doc.insert_pdf(orig_doc, from_page=pg_no, to_page=pg_no)

    return dedup_doc

if __name__ == "__main__":
    meta_info_list: list[dict] = []
    output_format: str = "csv"

    for orig_path, info in ORIG_PDF_PATHS.items():
        subject = info["subject"]
        difficulty = info["difficulty"]
        assert subject in ["Math", "R&W"], f"Subject('{subject}') must be either Math or R&W."
        assert difficulty in ["easy", "medium", "hard"], (
            f"Difficulty('{difficulty}') must be easy, medium, or hard"
        )

        meta_info_list.append({
            "parsed_at": str(dt.datetime.now()),
            "source_pdf": orig_path,
            "subject": subject,
            "difficulty": difficulty,
            "excluded": info["excluded"],
        })

        output_name = pdf_parsed_output_name(**info)
        timer.start()
        ssqb_infos: list[SSQBInfo] = parse_ssqb_pdfs(orig_path)
        df: pd.DataFrame = ssqb_infos_to_df(ssqb_infos)
        timer.stop(f"Completed parsing '{orig_path}'")

        dedup_doc: Document = dedup_ssqb_pdfs(orig_path)
        dedup_doc.save(dedup_pdf_output_path(orig_path))

        output_path = f"{output_name.lower()}.{output_format}"
        if output_format == "csv":
            df.to_csv(output_path, index=False)
        elif output_format == "json":
            df.to_json(output_path, index=False)
        else:
            print(f"Failed to export: Unknown format ('{output_format}')")
            print("Exporting to csv...")
            df.to_csv(output_path, index=False)

        timer.stop(f"Completed exporting '{orig_path}'\n-------------")

    with open("meta_infos.json", "w") as f:
        json.dump(meta_info_list, f, indent=4)
