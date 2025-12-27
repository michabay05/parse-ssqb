from dataclasses import dataclass, asdict
import datetime as dt
from pathlib import Path
import io, json, math, os, random, re, sys, time
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
    excluded: bool

    def __eq__(self, other) -> bool:
        # NOTE: Equality will be detected based on the ids; therefore this function
        #       assumes that each question has a UNIQUE id
        return isinstance(other, QInfo) and self.q_id == other.q_id

    def __hash__(self) -> int:
        return hash((self.q_id, self.domain, self.skill, self.pg_inds[0]))

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

def parse_question_pdf(path: str, excluded: bool) -> list[QInfo]:
    doc: Document = fitz.open(path)
    q_infos: list[QInfo] = []
    curr: QInfo = QInfo("", "", "", "easy", "", "", [], False)

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
                    pg_inds=curr.pg_inds,
                    excluded=excluded
                ))
                curr: QInfo = QInfo("", "", "", "easy", "", "", [], False)

            curr.q_id = matches[0]

            difficulty: Level | None = get_difficulty(doc, page, drawing_only=True)
            if difficulty is None:
                # This is a backup way of finding the difficulty; it should be able to find
                # out the difficulty purely through its drawings, but you never know . . .
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
        label_info_pat = r"Assessment (\w*) Test ([\w\s]*) Domain ([\w\s-]*) Skill ([\w\s,:-]*) D"
        matches = re.findall(label_info_pat, label_infos)
        if len(matches) == 1:
            assessment, test, domain, skill = matches[0]
            # NOTE: this is the same for all questions regardless of difficulty or subject
            # I'm just using it as a sanity check.
            assert assessment == "SAT"

            curr.test = test
            curr.domain = domain
            curr.skill = skill

    q_infos.append(curr)

    return q_infos

def parse_answer_pdf(path: str) -> list[AnsInfo]:
    doc: Document = fitz.open(path)
    a_infos: list[AnsInfo] = []
    curr: AnsInfo = AnsInfo(q_id="", answer="??", ans_src_pdf="", pg_inds=[])

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
                curr = AnsInfo(q_id="", answer="??", ans_src_pdf="", pg_inds=[])

            curr.q_id = matches[0]
        else:
            if curr.q_id == "":
                # This probably means that one question takes up multiple pages
                # print(f"No ID found in page {page_num + 1}")
                continue

        curr.pg_inds.append(page_ind)

        patterns = [
            # NOTE: I have the following patterns in case the first one does not match
            # 0: Should be common for MCQs and FRQs
            r"Correct Answer:[\s]([A-Za-z0-9.\/-]+)",
            # 1: Common for MCQs only
            r"Choice ([ABCDE]{1}) is correct\.",
            # 2: Common for FRQs only
            r"The correct answer is ([A-Za-z0-9.\/-]+)\.",
            # 3: For a specific question in adv math where a question asks for possible solutions
            r"The correct answer is either ([A-Za-z0-9.\/, -]+)\.",
        ]
        matches = []
        for pattern in patterns:
            matches = re.findall(pattern, text)
            if len(matches) > 0:
                break

        if len(matches) == 1:
            curr.answer = matches[0]

    return a_infos

def q_infos_to_df(q_infos: list[QInfo]) -> pd.DataFrame:
    # Convert to dataframe
    data: dict = {
        "ID": [],
        "Pages": [],
        "Difficulty": [],
        "Excluded": [],
        "Test": [],
        "Domain": [],
        "Skill": [],
        "Source_PDF": [],
    }
    for info in q_infos:
        data["ID"].append(info.q_id)
        data["Pages"].append(pages_as_str(info.pg_inds))
        data["Difficulty"].append(info.level)
        data["Excluded"].append(info.excluded)
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
        q_infos: list[QInfo] = parse_question_pdf(path, excluded)
        all_q_ids_so_far = [aq.q_id for aq in all_q_infos]
        for q_info in q_infos:
            # NOTE: if it is the second time, I come across this question, it must mean that
            # this question is both in the 'all' and 'excluded' list, therefore, delete the
            # existing q_info and add the excluded question. all_q_infos should only contain unique
            # items.
            try:
                ind = all_q_ids_so_far.index(q_info.q_id)
                del all_q_infos[ind]
            except ValueError:
                pass

            all_q_infos.append(q_info)

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
        all_a_ids_so_far = [aa.q_id for aa in all_a_infos]
        for a_info in a_infos:
            # NOTE: all_a_infos should contain only unique items
            if a_info.q_id not in all_a_ids_so_far:
                all_a_infos.append(a_info)

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
    all_df = pd.read_csv(path)
    q_infos: list[QInfo] = []

    for i in range(len(all_df)):
        pages_str = str(all_df["Pages"][i]) # type: ignore
        assert isinstance(pages_str, str)

        pages_str: list[str] = pages_str.split(PAGE_DELIMITER)
        pg_inds: list[int] = [int(pages_str[0]) - 1]
        for pg_no_str in pages_str[1:]:
            pg_inds.append(int(pg_no_str) - 1)

        q_id = all_df["ID"][i]
        test = all_df["Test"][i]
        domain = all_df["Domain"][i]
        level = all_df["Difficulty"][i]
        excluded = bool(all_df["Excluded"][i])
        skill = all_df["Skill"][i]
        src_pdf = all_df["Source_PDF"][i]

        assert isinstance(q_id, str), f"Expected q_id to be a str: q_id = '{q_id}'"
        assert isinstance(test, str), f"Expected test to be a str: test = '{test}' @ {i}"
        assert isinstance(domain, str), f"Expected domain to be a str: domain = '{domain}'"
        assert isinstance(level, str) and level in ["easy", "medium", "hard"], (
            f"Expected level to be a str: level = '{level}'"
        )
        assert isinstance(excluded, bool), f"Expected excluded to be a bool: excluded = '{excluded}'"
        assert isinstance(skill, str), f"Expected skill to be a str: skill = '{skill}'"
        assert isinstance(src_pdf, str), f"Expected src_pdf to be a str: src_pdf = '{src_pdf}'"

        q_infos.append(QInfo(
            q_id=q_id,
            test=test,
            domain=domain,
            skill=skill,
            level=level, # type: ignore
            excluded=excluded,
            src_pdf=src_pdf,
            pg_inds=pg_inds
        ))

    return q_infos

def import_a_parsed_info(path: str) -> list[AnsInfo]:
    all_df = pd.read_csv(path)
    a_infos: list[AnsInfo] = []

    for i in range(len(all_df)):
        pages_str = all_df["Pages"][i]
        assert isinstance(pages_str, str)

        pages: list[str] = pages_str.split(PAGE_DELIMITER)
        pg_inds: list[int] = []
        for pg_ind in pages:
            pg_inds.append(int(pg_ind) - 1)

        q_id = all_df["ID"][i]
        answer = all_df["Answer"][i]
        ans_src_pdf = all_df["Answer_PDF"][i]

        assert isinstance(q_id, str), f"Expected q_id to be a str: q_id: '{q_id}'"
        assert isinstance(answer, str), f"Expected answer to be a str: answer: '{answer}'"
        assert isinstance(ans_src_pdf, str), f"Expected ans_src_pdf to be a str: ans_src_pdf: '{ans_src_pdf}'"

        a_infos.append(AnsInfo(q_id=q_id, answer=answer, ans_src_pdf=ans_src_pdf, pg_inds=pg_inds))

    return a_infos

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
            skill = info.skill

            # NOTE: What an annoying bug. Can the college board really not make sure that they use a
            # consistent naming mechanism? I guess it's not suprising...
            if skill == "Cross-text Connections":
                skill = "Cross-Text Connections"

            if skill not in tree[info.test][info.domain]:
                tree[info.test][info.domain][skill] = 0

            tree[info.test][info.domain][skill] += 1

    with open(output_json, "w") as f:
        json.dump(tree, f, indent=4)

def put_answers_on_page(doc: Document, answers: list[tuple[str, str]]):
    # This was calculated assuming the page will have a DPI of 72
    width, height = (612, 792)
    pg = doc.new_page(width=width, height=height)

    margin = (48, 48)
    h_indent = 0.2 * margin[0]
    fsz = 13
    title_line_h = 2*fsz + 1*(2*fsz)
    pg.insert_text((margin[0], margin[1] + title_line_h), "Answer key", fontsize=2*fsz)


    line_h = fsz + 0.5*fsz
    total_vert_space = (height - (margin[1] + title_line_h)) - 2*margin[1]
    row_count = int(total_vert_space // line_h)
    col_count = math.ceil(len(answers) / row_count)

    row_h = line_h
    col_w = (width - (2*margin[0])) / col_count

    # i = r*width + c
    # i - c = r*width
    # (i - c) / width = r; given c
    for (i, (q_id, answer)) in enumerate(answers):
        r = i % row_count
        c = (i - r) / row_count
        # c = i % col_count
        # r = (i - c) / col_count
        pg.insert_text(
            # (start + c*col_w, start + r*row_h)
            point=((margin[0] + h_indent) + c*col_w, (margin[1] + title_line_h) + (r + 1)*row_h),
            # text=f"({i+1:4}) {q_id:9}; {answer}",
            text=f"{i+1:4}. {q_id:10}; {answer}",
            fontsize=fsz,
        )

def create_question_set(input_json: dict, q_infos: list[QInfo],
    a_infos: list[AnsInfo], shuffle: bool = True
) -> None:
    output_pdf_path: str = input_json["outputPath"]
    requested_count: int = input_json["totalQuestions"]
    specific_ids: list[str] = input_json["chosenIds"]
    all_chosen: list[QInfo] = []

    # Subject based filtering
    for test in ["RW", "Math"]:
        for domain, skills_info in input_json[test].items():
            for skill, qty in skills_info.items():
                # Find questions that test the expected skill
                valid_qs_inds: list[int] = []
                for i, q in enumerate(q_infos):
                    if q.domain == domain and q.skill == skill:
                        valid_qs_inds.append(i)

                if qty >= len(valid_qs_inds):
                    print(
                        f"For skill ({skill}), expected question count exceeds "
                        "questions that satisfy the requirement")
                    continue

                chosen_inds = random.choices(valid_qs_inds, k=min(qty, len(valid_qs_inds)))
                all_chosen.extend([q_infos[c_i] for c_i in chosen_inds])

    # Specific id filtering
    all_chosen_so_far = [chosen.q_id for chosen in all_chosen]
    for q_info in q_infos:
        if (q_info.q_id in specific_ids) and (q_info.q_id not in all_chosen_so_far):
            all_chosen.append(q_info)

    assert len(all_chosen) <= requested_count, (
        f"Questions that satisfy reqs ({len(all_chosen)}) <= Requested questions ({requested_count}): False"
    )

    if shuffle:
        random.shuffle(all_chosen)

    doc: Document = gen_pdf_from_q_infos(all_chosen)

    if len(a_infos) == 0:
        doc.save(output_pdf_path)
        return

    ans_list: list[tuple[str, str]] = []
    for chosen in all_chosen:
        for a_info in a_infos:
            if a_info.q_id == chosen.q_id:
                ans_list.append((a_info.q_id, a_info.answer))

    put_answers_on_page(doc, ans_list)
    doc.save(output_pdf_path)

def create_question_set_w_diff(input_json: dict, q_infos: list[QInfo],
    a_infos: list[AnsInfo], prob: dict[Level, float], shuffle: bool = True
) -> None:
    assert prob["easy"] + prob["medium"] + prob["hard"] == 1.0

    output_pdf_path: str = input_json["outputPath"]
    requested_count: int = input_json["totalQuestions"]
    specific_ids: list[str] = input_json["chosenIds"]
    qs_by_diff: dict[Level, list[int]] = {
        "easy": [],
        "medium": [],
        "hard": [],
    }

    # Subject based filtering
    for test in ["RW", "Math"]:
        for domain, skills_info in input_json[test].items():
            for skill, qty in skills_info.items():
                # Find questions that test the expected skill
                for i, q in enumerate(q_infos):
                    if q.domain == domain and q.skill == skill:
                        qs_by_diff[q.level].append(i)

    all_chosen: list[QInfo] = []
    max_random_q_count = requested_count - len(specific_ids)
    for diff, q_inds in qs_by_diff.items():
        n = int(max_random_q_count * prob[diff])
        all_chosen.extend([q_infos[ind] for ind in random.choices(q_inds, k=n)])

    # Specific id filtering
    all_chosen_so_far = [chosen.q_id for chosen in all_chosen]
    for q_info in q_infos:
        if (q_info.q_id in specific_ids) and (q_info.q_id not in all_chosen_so_far):
            all_chosen.append(q_info)

    assert len(all_chosen) <= requested_count, (
        f"Questions that satisfy reqs ({len(all_chosen)}) <= Requested questions ({requested_count}): False"
    )

    if shuffle:
        random.shuffle(all_chosen)

    doc: Document = gen_pdf_from_q_infos(all_chosen)

    if len(a_infos) == 0:
        doc.save(output_pdf_path)
        return

    ans_list: list[tuple[str, str]] = []
    for chosen in all_chosen:
        for a_info in a_infos:
            if a_info.q_id == chosen.q_id:
                ans_list.append((a_info.q_id, a_info.answer))

    put_answers_on_page(doc, ans_list)
    doc.save(output_pdf_path)

def gen_pdf_from_q_infos(ssqb_infos: list[QInfo]) -> Document:
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

    return out_pdf

def usage(program: str) -> None:
    print(f"USAGE: {program} <MODES> [ARGS]\n")
    print("Modes:")
    print("        qset <INPUT_JSON>  |  Generate question set given an input json for filtering")
    print("      allids <OUT_JSON>    |  Get a json containing the id of all questions")
    print("    parse-qs <OUT_CSV>     |  Categorize questions pdfs and output a single csv")
    print("    parse-as <OUT_CSV>      |  Categorize answers pdfs and output a single csv")
    print("   skilltree               |  Generate a skill tree with quantity; save into json")
    print("        help               |  Get this help message")

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

            q_infos: list[QInfo] = import_q_parsed_info("./all-q-parsed.csv")
            out_json: str = sys.argv[2]
            # The information about the question set's composition is found from the json
            with open("input.json", "r") as f:
                input_json = json.load(f)

            incl_ans_key = input_json["includeAnsKey"]
            assert isinstance(incl_ans_key, bool)
            a_infos: list[AnsInfo]  = []
            if incl_ans_key:
                a_infos = import_a_parsed_info("./all-a-parsed.csv")

            create_question_set(input_json, q_infos, a_infos)
            print(f"Complete! Exported PDF from filters at '{out_json}'")

        case "allids":
            if len(sys.argv) == 2:
                print("ERROR: please provide output txt to export ids to.")
                print("Try rerunning this command with the 'help' flag for more info.")
                sys.exit(1)

            q_infos: list[QInfo] = import_q_parsed_info("./all-q-parsed.csv")
            out_txt: str = sys.argv[2]
            export_all_qids(q_infos, sys.argv[2])
            print(f"Complete! Exported ids to '{out_txt}'")

        case "skilltree":
            q_infos: list[QInfo] = import_q_parsed_info("./all-q-parsed.csv")
            out_json: str = "skill-tree.json"
            gen_skill_tree(q_infos, out_json)
            print(f"Complete! Exported skill tree to '{out_json}'")

        case "derive-answers-from-qpdf":
            pdf_path = "./stand-engl-conv-exam.pdf"
            out_path = "./stand-engl-conv-exam-w-ans.pdf"
            # q_infos: list[QInfo] = import_q_parsed_info("./all-q-parsed.csv")
            q_infos: list[QInfo] = parse_question_pdf(pdf_path, False)
            a_infos = import_a_parsed_info("./all-a-parsed.csv")

            ans_list: list[tuple[str, str]] = []
            for chosen in q_infos:
                for a_info in a_infos:
                    if a_info.q_id == chosen.q_id:
                        ans_list.append((a_info.q_id, a_info.answer))

            doc = Document()
            put_answers_on_page(doc, ans_list)
            doc.save(out_path)

        case "custom":
            q_infos: list[QInfo] = import_q_parsed_info("./all-q-parsed.csv")
            # The information about the question set's composition is found from the json
            with open("input.json", "r") as f:
                input_json = json.load(f)

            incl_ans_key = input_json["includeAnsKey"]
            assert isinstance(incl_ans_key, bool)
            a_infos: list[AnsInfo]  = []
            if incl_ans_key:
                a_infos = import_a_parsed_info("./all-a-parsed.csv")

            with open("input.json", "r") as f:
                input_json = json.load(f)

            create_question_set_w_diff(input_json, q_infos, a_infos, {
                "easy": 0.1,
                "medium": 0.5,
                "hard": 0.4,
            })
            print(f"[Custom] Complete! Exported PDF from filters.")

        case "help":
            usage(sys.argv[0])

        case "_":
            usage(sys.argv[0])
            print(f"\nERROR: Unknown mode: '{mode}'")
