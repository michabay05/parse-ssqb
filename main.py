from dataclasses import dataclass, asdict
import datetime as dt
import io
from pathlib import Path
import json, os, random, re, sys, time
from typing import Literal

import pandas as pd
import fitz
from pymupdf import Document, Page
from PIL import Image

# Code used to select all checkboxes
# ======================================================
# const delay = (ms) => {
#     return new Promise(resolve => setTimeout(resolve, ms));
# }
# const clickAllBoxes = () => {
#     document
#         .getElementById("results-table")
#         .querySelectorAll('input[type="checkbox"]')
#         .forEach(checkbox => {
#             checkbox.checked = true; // Check the checkbox
#             checkbox.click(); // Simulate a click event
#     });
# }
# (async () => {
#     for (let i = 0; i < 33; i++) {
#         clickAllBoxes();
#         console.log(`Moving on from page ${i + 1}`);
#         await delay(5000);
#         document.getElementById("undefined_next").click();
#     }
#     clickAllBoxes();
# })();

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

@dataclass
class FileInfo:
    subject: str
    difficulty: Level
    excluded: bool


def pdf_parsed_output_name(info: FileInfo) -> str:
    excluded_str = "excluded" if info.excluded else ""

    return f"./parsed/{info.subject}-{excluded_str}-{info.difficulty}"

def dedup_pdf_output_path(orig_pdf_path: str) -> str:
    return f"./dedup/dedup-{'-'.join(orig_pdf_path.split('-')[1:])}"

PDF_PATHS: dict[str, FileInfo] = {
    "./dedup/dedup-math-excluded-easy.pdf": FileInfo("Math", "easy", True),
    "./dedup/dedup-math-excluded-medium.pdf": FileInfo("Math", "medium", True),
    "./dedup/dedup-math-excluded-hard.pdf": FileInfo("Math", "hard", True),
    "./dedup/dedup-rw-excluded-easy.pdf": FileInfo("RW", "easy", True),
    "./dedup/dedup-rw-excluded-medium.pdf": FileInfo("RW", "medium", True),
    "./dedup/dedup-rw-excluded-hard.pdf": FileInfo("RW", "hard", True)
}

timer: Timer = Timer()
PAGE_DELIMITER: str = "_"

@dataclass
class SSQBInfo:
    q_id: str
    test: str
    domain: str
    level: Level
    skill: str
    src_pdf: str
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

from pprint import pprint
# def get_difficulty(page: Page, drawing_only: bool = False) -> Level | None:
def get_difficulty(doc: Document, page: Page, drawing_only: bool = False) -> Level | None:
    count: int = 0

    if drawing_only:
        # Look for this color
        diff_d_color: tuple[float, float, float] = (0.0, 0.37254899740219116, 0.6274510025978088)
        drawings = page.get_drawings()
        for d in drawings:
            if d["fill"] == diff_d_color:
                count += 1
    else:
        found_usable: bool = False
        # Look for this color
        diff_i_color: tuple[int, int, int] = (0, 83, 155)
        image_list = page.get_images(full=True)
        assert len(image_list) > 0, "Can find difficulty; no image on the pdf"

        for image_index, img in enumerate(image_list):
            xref = img[0]
            base_image = doc.extract_image(xref)
            img_bytes = base_image["image"]
            pil_img = Image.open(io.BytesIO(img_bytes))
            if pil_img.width != 46:
                continue

            found_usable = True

            # To determine the difficulty, I am going to sample 3 specific pixels
            # and depending on its color, I will determine the page's labeled difficulty
            y = int(pil_img.height / 2)
            for x in [5, pil_img.width / 2, pil_img.width - 5]:
                color = pil_img.getpixel((int(x), y))
                assert isinstance(color, tuple)
                if color == diff_i_color:
                    count += 1

        if not found_usable:
            print(f"I could not find any good image to interpret the difficulty.")

    match count:
        case 1: return "easy"
        case 2: return "medium"
        case 3: return "hard"
        case _: return None

def parse_ssqb_pdfs(path: str) -> list[SSQBInfo]:
    assert path in PDF_PATHS.keys(), f"Unknown path: '{path}'"
    # difficulty: str = PDF_PATHS[path].difficulty
    # assert False, "Use new difficulty function above"

    doc: Document = fitz.open(path)
    last_page_ind: int = 0
    q_infos: list[SSQBInfo] = []

    for page_ind in range(len(doc)):
        page = doc.load_page(page_ind)
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
        if page_ind - last_page_ind > 1:
            page_inds = [last_page_ind + 1, page_ind]
        else:
            page_inds = [page_ind]

        last_page_ind = page_ind
        q_id: str = matches[0]

        difficulty: Level | None = get_difficulty(doc, page, drawing_only=True)
        if difficulty is None:
            difficulty: Level | None = get_difficulty(doc, page, drawing_only=False)
            assert difficulty is not None, f"[{path}, pg: {page_ind + 1}] Unable to find difficulty"

        label_infos = ' '.join(text[labels:].split())
        label_info_pat = r"Assessment (\w*) Test ([\w\s]*) Domain ([\w\s]*) Skill ([\w\s]*) D"
        matches = re.findall(label_info_pat, label_infos)
        for mat in matches:
            assessment, test, domain, skill = mat
            assert assessment == "SAT"
            q_infos.append(SSQBInfo(
                q_id=q_id,
                test=test,
                domain=domain,
                skill=skill,
                src_pdf=path,
                level=difficulty,
                page_inds=page_inds
            ))

    return q_infos

def ssqb_infos_to_df(ssqb_infos: list[SSQBInfo]) -> pd.DataFrame:
    # Convert to dataframe
    data: dict = {
        "ID": [],
        "Pages": [],
        "Difficulty": [],
        "Test": [],
        "Domain": [],
        "Skill": [],
        "Source_PDF": [],
    }
    for info in ssqb_infos:
        data["ID"].append(info.q_id)
        data["Pages"].append(info.pages_as_str())
        data["Difficulty"].append(info.level)
        data["Test"].append(info.test)
        data["Domain"].append(info.domain)
        data["Skill"].append(info.skill)
        data["Source_PDF"].append(info.src_pdf)

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

def parse_all_ssqb_pdfs(out_csv: str) -> None:
    meta_info_list: list[dict] = []
    all_ssqb_infos: list[SSQBInfo] = []

    for orig_path, info in PDF_PATHS.items():
        subject = info.subject
        difficulty = info.difficulty
        assert subject in ["Math", "RW"], f"Subject('{subject}') must be either Math or RW."
        assert difficulty in ["easy", "medium", "hard"], (
            f"Difficulty('{difficulty}') must be easy, medium, or hard"
        )

        meta_info_list.append({
            "parsed_at": str(dt.datetime.now()),
            "source_pdf": orig_path,
            "subject": subject,
            "difficulty": difficulty,
            "excluded": info.excluded,
        })

        output_name = pdf_parsed_output_name(info)
        timer.start()
        ssqb_infos: list[SSQBInfo] = parse_ssqb_pdfs(orig_path)
        all_ssqb_infos.extend(ssqb_infos)
        df: pd.DataFrame = ssqb_infos_to_df(ssqb_infos)
        timer.stop(f"Completed parsing '{orig_path}'")

        # NOTE: deduplication does not have to always happen
        # dedup_doc: Document = dedup_ssqb_pdfs(orig_path)
        # dedup_doc.save(dedup_pdf_output_path(orig_path))

        output_path = f"{output_name.lower()}.csv"
        df.to_csv(output_path, index=False)

        timer.stop(f"Completed exporting '{orig_path}'\n-------------")

    combined_df: pd.DataFrame = ssqb_infos_to_df(all_ssqb_infos)
    combined_df.to_csv(out_csv, index=False)

    with open("meta_infos.json", "w") as f:
        json.dump(meta_info_list, f, indent=4)

def import_parsed_info() -> list[SSQBInfo]:
    # df_list: list[pd.DataFrame] = []
    # NOTE: changed to using a combined csv file instead of six smaller ones
    # dir: str = "./parsed"
    # for file_path in os.listdir(dir):
    #     path = f"{dir}/{file_path}"
    #     if Path(path).suffix != ".csv":
    #         print(f"Ignoring other files found: '{path}'")
    #         continue

    #     df_list.append(pd.read_csv(path))
    # all_df = pd.concat(df_list, ignore_index=True)

    all_df = pd.read_csv("./parsed/combined_infos.csv")
    ssqb_infos: list[SSQBInfo] = []

    for i in range(len(all_df)):
        pages_str = str(all_df["Pages"][i]) # type: ignore
        assert isinstance(pages_str, str)
        pages_str: list[str] = pages_str.split(PAGE_DELIMITER)
        assert len(pages_str) == 1 or len(pages_str) == 2

        page_inds: list[int] = [int(pages_str[0]) - 1]
        if len(pages_str) == 2:
            page_inds.append(int(pages_str[1]) - 1)

        ssqb_infos.append(SSQBInfo(
            q_id=all_df["ID"][i], # type: ignore
            test=all_df["Test"][i], # type: ignore
            domain=all_df["Domain"][i], # type: ignore
            level=all_df["Difficulty"][i], # type: ignore
            skill=all_df["Skill"][i], # type: ignore
            src_pdf=all_df["Source_PDF"][i], # type: ignore
            page_inds=page_inds
        ))

    return ssqb_infos

def gen_skill_tree(ssqb_infos: list[SSQBInfo], output_json: str) -> None:
    tree: dict[str, dict[str, dict[str, int]]] = {}
    for info in ssqb_infos:
        if info.test not in tree.keys():
            tree[info.test] = {}

        if info.domain not in tree[info.test].keys():
            tree[info.test][info.domain] = {}

        if info.skill not in tree[info.test][info.domain]:
            tree[info.test][info.domain][info.skill] = 0

        tree[info.test][info.domain][info.skill] += 1

    with open(output_json, "w") as f:
        json.dump(tree, f, indent=4)

def create_question_set(json_path: str, ssqb_infos: list[SSQBInfo]) -> None:
    # The information about the question set's composition is found from the json
    with open(json_path, "r") as f:
        set_info = json.load(f)

    output_pdf_path: str = set_info["outputPath"]
    total_questions: int = set_info["totalQuestions"]
    specific_ids: list[str] = set_info["chosenIds"]
    all_chosen: list[SSQBInfo] = []

    # Subject based filtering
    for test in ["RW", "Math"]:
        for domain, skills_info in set_info[test].items():
            for skill, qty in skills_info.items():
                # Find questions that test the expected skill
                valid_qs_inds: list[int] = []
                for i, q in enumerate(ssqb_infos):
                    if q.domain == domain and q.skill == skill:
                        valid_qs_inds.append(i)

                if qty >= len(valid_qs_inds):
                    print(
                        f"For skill ({skill}), expected question count exceeds "
                        "questions that satisfy the requirement")
                    continue

                chosen_inds = random.choices(valid_qs_inds, k=min(qty, len(valid_qs_inds)))
                all_chosen.extend([ssqb_infos[c_i] for c_i in chosen_inds])

    # Specific id filtering
    all_chosen_so_far = [ssqb.q_id for ssqb in all_chosen]
    for ssqb in ssqb_infos:
        if (ssqb.q_id in specific_ids) and (ssqb.q_id not in all_chosen_so_far):
            all_chosen.append(ssqb)

    assert len(all_chosen) <= total_questions, (
        f"Requested questions ({total_questions}) && Provided questions ({len(all_chosen)})"
    )
    gen_pdf_from_ssqb_infos(all_chosen, output_pdf_path)

def gen_pdf_from_ssqb_infos(ssqb_infos: list[SSQBInfo], output_pdf_path: str) -> None:
    out_pdf: Document = Document()

    print(f"Saving {len(ssqb_infos)} questions...")

    path_to_docs: dict[str, Document] = {}
    for ssqb in ssqb_infos:
        if ssqb.src_pdf not in path_to_docs.keys():
            path_to_docs[ssqb.src_pdf] = fitz.open(ssqb.src_pdf)

        doc: Document = path_to_docs[ssqb.src_pdf]
        page_nos: list[int] = ssqb.page_inds
        if len(page_nos) == 1:
            page_nos.append(page_nos[0])

        assert len(page_nos) == 2, f"A page range should have only 2 numbers -> pages: {page_nos}"

        for pg_no in range(page_nos[0], page_nos[1] + 1):
            if not is_page_empty(doc.load_page(pg_no)):
                out_pdf.insert_pdf(doc, from_page=pg_no, to_page=pg_no)

    out_pdf.save(output_pdf_path)

def usage(program: str) -> None:
    print(f"USAGE: {program} [MODES] [ARGS]\n")
    print("Modes:")
    print("        qset [INPUT_JSON]  |  Generate question set given an input json for filtering")
    print("       allids [OUT_JSON]   |  Get a json containing the id of all questions")
    print("  categorize [OUT_CSV]     |  Categorize all the questions and output a single csv")

def export_all_qids(ssqb_infos: list[SSQBInfo], out_path: str) -> None:
    all_ids: list[str] = [ssqb.q_id for ssqb in ssqb_infos]
    with open(out_path, "w") as f:
        json.dump({"qIds": all_ids}, f, indent=4)

if __name__ == "__main__":
    if len(sys.argv) == 1:
        usage(sys.argv[0])
        sys.exit(1)

    mode: str = sys.argv[1]
    match mode:
        case "categorize":
            if len(sys.argv) == 2:
                print("ERROR: please provide output csv to export parsed info into.")
                print("Try rerunning this command with the 'help' flag for more info.")
                sys.exit(1)

            out_csv: str = sys.argv[2]
            parse_all_ssqb_pdfs(out_csv)
            print(f"Complete! Exported PDF info to '{out_csv}'")

        case "qset":
            if len(sys.argv) == 2:
                print("ERROR: please provide input json to use for filtering.")
                print("Try rerunning this command with the 'help' flag for more info.")
                sys.exit(1)

            ssqb_infos: list[SSQBInfo] = import_parsed_info()
            out_json: str = sys.argv[2]
            create_question_set(out_json, ssqb_infos)
            print(f"Complete! Exported PDF to '{out_json}'")

        case "allids":
            if len(sys.argv) == 2:
                print("ERROR: please provide output txt to export ids to.")
                print("Try rerunning this command with the 'help' flag for more info.")
                sys.exit(1)

            ssqb_infos: list[SSQBInfo] = import_parsed_info()
            out_txt: str = sys.argv[2]
            export_all_qids(ssqb_infos, sys.argv[2])
            print(f"Complete! Exported ids to '{out_txt}'")

        case "help":
            print(f"Unknown mode: '{mode}'")

    # parse_all_ssqb_pdfs()
    # gen_skill_tree(ssqb_info, "skill-tree.json")
