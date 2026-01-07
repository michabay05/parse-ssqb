from dataclasses import dataclass
import datetime as dt
import io, json, re, time
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
