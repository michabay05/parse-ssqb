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
#     for (let i = 0; i < _; i++) {
#         clickAllBoxes();
#         console.log(`Moving on from page ${i + 1}`);
#         await delay(3000);
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

# @dataclass
# class FileInfo:
#     subject: str
#     difficulty: Level
#     excluded: bool

# def pdf_parsed_output_name(info: FileInfo) -> str:
#     excluded_str = "excluded" if info.excluded else ""

#     return f"./parsed/{info.subject}-{excluded_str}-{info.difficulty}"

# def dedup_pdf_output_path(orig_pdf_path: str) -> str:
#     return f"./dedup/dedup-{'-'.join(orig_pdf_path.split('-')[1:])}"

# PDF_PATHS: dict[str, FileInfo] = {
#     "./dedup/dedup-math-excluded-easy.pdf": FileInfo("Math", "easy", True),
#     "./dedup/dedup-math-excluded-medium.pdf": FileInfo("Math", "medium", True),
#     "./dedup/dedup-math-excluded-hard.pdf": FileInfo("Math", "hard", True),
#     "./dedup/dedup-rw-excluded-easy.pdf": FileInfo("RW", "easy", True),
#     "./dedup/dedup-rw-excluded-medium.pdf": FileInfo("RW", "medium", True),
#     "./dedup/dedup-rw-excluded-hard.pdf": FileInfo("RW", "hard", True)
# }

timer: Timer = Timer()
PAGE_DELIMITER: str = "_"

def pages_as_str(page_inds: list[int]) -> str:
    if len(page_inds) == 0:
        return ""

    pg_str: str = str(page_inds[0] + 1)
    for pg_ind in page_inds[1:]:
        pg_str += PAGE_DELIMITER + str(pg_ind + 1)

    return pg_str

@dataclass
class QInfo:
    q_id: str
    test: str
    domain: str
    level: Level
    skill: str
    src_pdf: str
    pg_inds: list[int]

    # def __eq__(self, other) -> bool:
    #     # NOTE: Equality will be detected based on the ids; therefore this function
    #     #       assumes that each question has a UNIQUE id
    #     return isinstance(other, QInfo) and self.q_id == other.q_id

    # def __hash__(self) -> int:
    #     return hash((self.q_id, self.domain, self.skill, self.page_inds[0]))

@dataclass
class AnsInfo:
    q_id: str
    answer: str
    ans_src_pdf: str
    pg_inds: list[int]


def is_page_empty(page: Page) -> bool:
    page_text = page.get_text()
    assert isinstance(page_text, str)

    has_text = bool(page_text.strip())
    has_images = bool(page.get_images())
    # has_drawings = bool(page.get_drawings())

    return not (bool(has_text) or bool(has_images))

def get_difficulty(doc: Document, page: Page, drawing_only: bool) -> Level | None:
    count: int = 0

    if drawing_only:
        # Look for this color
        diff_d_color: tuple[float, float, float] = (0.0, 0.37254899740219116, 0.6274510025978088)
        drawings = page.get_drawings()
        def close(a: float, b: float) -> bool:
            return abs(a - b) < 5e-5

        for d in drawings:
            color = d["fill"]
            if color is None:
                continue

            if (close(color[0], diff_d_color[0])
                and close(color[1], diff_d_color[1])
                and close(color[2], diff_d_color[2])):
                count += 1
    else:
        # Look for this color
        diff_i_color: tuple[int, int, int] = (0, 83, 155)
        image_list = page.get_images(full=True)
        if len(image_list) == 0:
            print("No images found.")
            return None

        found_usable: bool = False
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

def parse_question_pdf(path: str) -> list[QInfo]:
    doc: Document = fitz.open(path)
    q_infos: list[QInfo] = []
    curr: QInfo = QInfo("", "", "", "easy", "", "", [])

    for page_ind in range(len(doc)):
        page = doc.load_page(page_ind)
        if is_page_empty(page):
            # Skip pages that are empty
            continue

        text = page.get_text()
        assert isinstance(text, str)

        q_id_pat: str = r"Question ID ([0-9a-f]{8})"
        matches = re.findall(q_id_pat, text)
        if len(matches) == 1:
            if curr.q_id != "":
                q_infos.append(QInfo(
                    q_id=curr.q_id,
                    test=curr.test,
                    domain=curr.domain,
                    skill=curr.skill,
                    src_pdf=path,
                    level=curr.level,
                    pg_inds=curr.pg_inds
                ))
                curr: QInfo = QInfo("", "", "", "easy", "", "", [])

            curr.q_id = matches[0]

            difficulty: Level | None = get_difficulty(doc, page, drawing_only=True)
            if difficulty is None:
                # This is a backup way of finding the difficulty; I should be to find out the
                # difficulty purely through its drawings, but you never know . . .
                difficulty: Level | None = get_difficulty(doc, page, drawing_only=False)
                assert difficulty is not None, f"[{path}, pg: {page_ind + 1}] Unable to find difficulty"

            curr.level = difficulty
        else:
            if curr.q_id == "":
                # This probably means that one question takes up multiple pages
                # print(f"No ID found in page {page_num + 1}")
                continue

        curr.pg_inds.append(page_ind)

        labels_start_ind: int = text.find("Assessment")
        label_infos = ' '.join(text[labels_start_ind:].split())
        label_info_pat = r"Assessment (\w*) Test ([\w\s]*) Domain ([\w\s]*) Skill ([\w\s]*) D"
        matches = re.findall(label_info_pat, label_infos)
        if len(matches) == 1:
            assessment, test, domain, skill = matches[0]
            # NOTE: this is the same for all questions regardless of difficulty or subject
            # I'm just using it as a sanity check.
            assert assessment == "SAT"

            curr.test = test
            curr.domain = domain
            curr.skill = skill

    return q_infos

def parse_answer_pdf(path: str) -> list[AnsInfo]:
    # NOTE: I have the following patterns in case the first one does not match
    # 1: Should be common for MCQs and FRQs
    first_pat: str = r"Correct Answer:[\s]([A-Za-z0-9.\/]+)"
    # 2: Common for MCQs only
    second_pat: str = r"Choice ([ABCDE]{1}) is correct\."
    # 3: Common for FRQs only
    third_pat: str = r"The correct answer is ([A-Za-z0-9.\/]+)\."

    doc: Document = fitz.open(path)
    a_infos: list[AnsInfo] = []
    curr: AnsInfo = AnsInfo("", "", "", [])

    for page_ind in range(len(doc)):
        page = doc.load_page(page_ind)
        if is_page_empty(page):
            continue

        text = page.get_text()
        assert isinstance(text, str)

        q_id_pat: str = r"Question ID ([0-9a-f]{8})"
        matches = re.findall(q_id_pat, text)
        if len(matches) == 1:
            if curr.q_id != "":
                a_infos.append(AnsInfo(curr.q_id, curr.answer, path, curr.pg_inds))
                curr = AnsInfo("", "", "", [])

            curr.q_id = matches[0]
        else:
            if curr.q_id == "":
                # This probably means that one question takes up multiple pages
                # print(f"No ID found in page {page_num + 1}")
                continue

        curr.pg_inds.append(page_ind)

        matches = []
        for pattern in [first_pat, second_pat, third_pat]:
        # for (i, pattern) in enumerate([first_pat, second_pat, third_pat]):
            matches = re.findall(pattern, text)
            if len(matches) > 0:
                # print(f"Using pattern {i + 1}")
                break

        if len(matches) == 1:
            curr.answer = matches[0]

    return a_infos

def q_infos_to_df(ssqb_infos: list[QInfo]) -> pd.DataFrame:
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
        data["Pages"].append(pages_as_str(info.pg_inds))
        data["Difficulty"].append(info.level)
        data["Test"].append(info.test)
        data["Domain"].append(info.domain)
        data["Skill"].append(info.skill)
        data["Source_PDF"].append(info.src_pdf)

    return pd.DataFrame(data)

def a_infos_to_df(a_infos: list[AnsInfo]) -> pd.DataFrame:
    # Convert to dataframe
    data: dict = {
        "ID": [],
        "Answer": [],
        "Pages": [],
        "Answer_PDF": [],
    }
    for a in a_infos:
        data["ID"].append(a.q_id)
        data["Answer"].append(a.answer)
        data["Pages"].append(pages_as_str(a.pg_inds))
        data["Answer_PDF"].append(a.ans_src_pdf)

    return pd.DataFrame(data)

def dedup_q_pdfs(pdf_path: str) -> Document:
    ssqb_infos: list[QInfo] = parse_question_pdf(pdf_path)
    assert len(ssqb_infos) > 0, "Parsed ssqb info should have some objects in it."

    dedup_ssqb: list[QInfo] = []
    for ssqb in ssqb_infos:
        if ssqb not in dedup_ssqb:
            dedup_ssqb.append(ssqb)

    orig_doc: Document = fitz.open(pdf_path)
    dedup_doc: Document = Document()

    for ssqb in dedup_ssqb:
        page_nos: list[int] = ssqb.pg_inds
        if len(page_nos) == 1:
            page_nos.append(page_nos[0])

        assert len(page_nos) == 2, f"A page range should have only 2 numbers -> pages: {page_nos}"

        for pg_no in range(page_nos[0], page_nos[1] + 1):
            if not is_page_empty(orig_doc.load_page(pg_no)):
            # if not is_page_empty(orig_doc.load_page(pg_no)):
                dedup_doc.insert_pdf(orig_doc, from_page=pg_no, to_page=pg_no)

    return dedup_doc

def parse_all_q_pdfs(file_paths: list[tuple[str, bool]], out_csv: str) -> None:
    meta_info_list: list[dict] = []
    all_q_infos: list[QInfo] = []

    for path, excluded in file_paths:
        meta_info_list.append({
            "parsed_at": str(dt.datetime.now()),
            "source_pdf": path,
            "excluded": excluded,
        })

        # output_name = pdf_parsed_output_name(path)
        timer.start()
        q_infos: list[QInfo] = parse_question_pdf(path)
        all_q_infos.extend(q_infos)
        timer.stop(f"Completed parsing '{path}'")

        # NOTE: deduplication does not have to always happen
        # dedup_doc: Document = dedup_ssqb_pdfs(path)
        # dedup_doc.save(dedup_pdf_output_path(path))

        # NOTE: For now, I don't think I need to export parsed info for each file individually
        # output_path = f"{output_name.lower()}.csv"
        # df.to_csv(output_path, index=False)

    combined_df: pd.DataFrame = q_infos_to_df(all_q_infos)
    combined_df.to_csv(out_csv, index=False)

    with open("q_meta_infos.json", "w") as f:
        json.dump(meta_info_list, f, indent=4)

def parse_all_a_pdfs(file_paths: list[tuple[str, bool]], out_csv: str) -> None:
    meta_info_list: list[dict] = []
    all_a_infos: list[AnsInfo] = []

    for path, excluded in file_paths:
        meta_info_list.append({
            "parsed_at": str(dt.datetime.now()),
            "source_pdf": path,
            "excluded": excluded,
        })

        # output_name = pdf_parsed_output_name(path)
        timer.start()
        a_infos: list[AnsInfo] = parse_answer_pdf(path)
        all_a_infos.extend(a_infos)
        timer.stop(f"Completed parsing '{path}'")

        # NOTE: deduplication does not have to always happen
        # dedup_doc: Document = dedup_ssqb_pdfs(path)
        # dedup_doc.save(dedup_pdf_output_path(path))

        # NOTE: For now, I don't think I need to export parsed info for each file individually
        # output_path = f"{output_name.lower()}.csv"
        # df.to_csv(output_path, index=False)

    combined_df: pd.DataFrame = a_infos_to_df(all_a_infos)
    combined_df.to_csv(out_csv, index=False)

    with open("a_meta_infos.json", "w") as f:
        json.dump(meta_info_list, f, indent=4)

def import_q_parsed_info(path: str) -> list[QInfo]:
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

    all_df = pd.read_csv(path)
    ssqb_infos: list[QInfo] = []

    for i in range(len(all_df)):
        pages_str = str(all_df["Pages"][i]) # type: ignore
        assert isinstance(pages_str, str)
        pages_str: list[str] = pages_str.split(PAGE_DELIMITER)
        assert len(pages_str) == 1 or len(pages_str) == 2

        page_inds: list[int] = [int(pages_str[0]) - 1]
        if len(pages_str) == 2:
            page_inds.append(int(pages_str[1]) - 1)

        ssqb_infos.append(QInfo(
            q_id=all_df["ID"][i], # type: ignore
            test=all_df["Test"][i], # type: ignore
            domain=all_df["Domain"][i], # type: ignore
            level=all_df["Difficulty"][i], # type: ignore
            skill=all_df["Skill"][i], # type: ignore
            src_pdf=all_df["Source_PDF"][i], # type: ignore
            pg_inds=page_inds
        ))

    return ssqb_infos

def gen_skill_tree(ssqb_infos: list[QInfo], output_json: str, w_difficulty: bool = False) -> None:
    tree: dict[str, dict[str, dict]] = {}
    for info in ssqb_infos:
        if info.test not in tree.keys():
            tree[info.test] = {}

        if info.domain not in tree[info.test].keys():
            tree[info.test][info.domain] = {}


        if w_difficulty:
            if info.skill not in tree[info.test][info.domain]:
                tree[info.test][info.domain][info.skill] = [0, 0, 0]

            ind = -1
            match info.level:
                case "easy":
                    ind = 0
                case "medium":
                    ind = 1
                case "hard":
                    ind = 2

            tree[info.test][info.domain][info.skill][ind] += 1
        else:
            if info.skill not in tree[info.test][info.domain]:
                tree[info.test][info.domain][info.skill] = 0

            tree[info.test][info.domain][info.skill] += 1

    with open(output_json, "w") as f:
        json.dump(tree, f, indent=4)

def create_question_set(json_path: str, ssqb_infos: list[QInfo]) -> None:
    # The information about the question set's composition is found from the json
    with open(json_path, "r") as f:
        set_info = json.load(f)

    output_pdf_path: str = set_info["outputPath"]
    total_questions: int = set_info["totalQuestions"]
    specific_ids: list[str] = set_info["chosenIds"]
    all_chosen: list[QInfo] = []

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

def gen_pdf_from_ssqb_infos(ssqb_infos: list[QInfo], output_pdf_path: str) -> None:
    out_pdf: Document = Document()

    print(f"Saving {len(ssqb_infos)} questions...")

    path_to_docs: dict[str, Document] = {}
    for ssqb in ssqb_infos:
        if ssqb.src_pdf not in path_to_docs.keys():
            path_to_docs[ssqb.src_pdf] = fitz.open(ssqb.src_pdf)

        doc: Document = path_to_docs[ssqb.src_pdf]
        page_nos: list[int] = ssqb.pg_inds
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
    print("        qset <INPUT_JSON> |  Generate question set given an input json for filtering")
    print("      allids <OUT_JSON>   |  Get a json containing the id of all questions")
    print("    parse-qs <OUT_CSV>    |  Categorize questions pdfs and output a single csv")
    print("   parse-as <OUT_CSV>    |  Categorize answers pdfs and output a single csv")
    print("   skilltree              |  Generate a skill tree with quantity; save into json")
    print("        help              |  Get this help message")

def export_all_qids(ssqb_infos: list[QInfo], out_path: str) -> None:
    all_ids: list[str] = [ssqb.q_id for ssqb in ssqb_infos]
    with open(out_path, "w") as f:
        json.dump({"qIds": all_ids}, f, indent=4)

if __name__ == "__main__":
    if len(sys.argv) == 1:
        usage(sys.argv[0])
        sys.exit(1)

    mode: str = sys.argv[1]
    match mode:
        case "parse-qs":
            if len(sys.argv) == 2:
                print("ERROR: please provide output csv to export parsed info into.")
                print("Try rerunning this command with the 'help' flag for more info.")
                sys.exit(1)

            file_paths: list[tuple[str, bool]] = []
            for dir_ind, dir in enumerate(["./alls/questions/", "./excludeds/questions/"]):
                for aqp in os.listdir(dir):
                    p = Path(dir) / aqp
                    file_paths.append((str(p), dir_ind == 1))

            out_csv: str = sys.argv[2]
            parse_all_q_pdfs(file_paths, out_csv)
            print(f"Complete! Exported question PDFs info to '{out_csv}'")

        case "parse-as":
            if len(sys.argv) == 2:
                print("ERROR: please provide output csv to export parsed info into.")
                print("Try rerunning this command with the 'help' flag for more info.")
                sys.exit(1)

            file_paths: list[tuple[str, bool]] = []
            for dir_ind, dir in enumerate(["./alls/answers/", "./excludeds/answers/"]):
                for aqp in os.listdir(dir):
                    p = Path(dir) / aqp
                    file_paths.append((str(p), dir_ind == 1))

            out_csv: str = sys.argv[2]
            parse_all_a_pdfs(file_paths, out_csv)

            print(f"Complete! Exported answer PDFs info to '{out_csv}'")

        case "qset":
            if len(sys.argv) == 2:
                print("ERROR: please provide input json to use for filtering.")
                print("Try rerunning this command with the 'help' flag for more info.")
                sys.exit(1)

            ssqb_infos: list[QInfo] = import_q_parsed_info("./all-q-parsed.csv")
            out_json: str = sys.argv[2]
            create_question_set(out_json, ssqb_infos)
            print(f"Complete! Exported PDF to '{out_json}'")

        case "allids":
            if len(sys.argv) == 2:
                print("ERROR: please provide output txt to export ids to.")
                print("Try rerunning this command with the 'help' flag for more info.")
                sys.exit(1)

            ssqb_infos: list[QInfo] = import_q_parsed_info("./all-q-parsed.csv")
            out_txt: str = sys.argv[2]
            export_all_qids(ssqb_infos, sys.argv[2])
            print(f"Complete! Exported ids to '{out_txt}'")

        case "skilltree":
            ssqb_infos: list[QInfo] = import_q_parsed_info("./all-q-parsed.csv")
            out_json: str = "skill-tree.json"
            gen_skill_tree(ssqb_infos, out_json)
            print(f"Complete! Exported skill tree to '{out_json}'")

        case "help":
            usage(sys.argv[0])

        case "_":
            usage(sys.argv[0])
            print(f"\nERROR: Unknown mode: '{mode}'")
