from pathlib import Path
import json, math, os, random, sys

import fitz
from pymupdf import Document

import prepare
from prepare import AnsInfo, Level, QInfo

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
            if not prepare.is_page_empty(doc.load_page(pg_no)):
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
    q_infos: list[QInfo] = prepare.import_q_parsed_info("./all-q-parsed.csv")
    a_infos: list[AnsInfo] = prepare.import_a_parsed_info("./all-a-parsed.csv")

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
            prepare.parse_all_q_pdfs(file_paths, out_csv)
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
            prepare.parse_all_a_pdfs(file_paths, out_csv)
            print(f"Complete! Exported answer PDFs info to '{out_csv}'")

        case "qset":
            if len(sys.argv) == 2:
                print("ERROR: please provide input json to use for filtering.")
                print("Try rerunning this command with the 'help' flag for more info.")
                sys.exit(1)

            out_json: str = sys.argv[2]
            # The information about the question set's composition is found from the json
            with open("input.json", "r") as f:
                input_json = json.load(f)

            incl_ans_key = input_json["includeAnsKey"]
            assert isinstance(incl_ans_key, bool)

            create_question_set(input_json, q_infos, a_infos if incl_ans_key else [])
            print(f"Complete! Exported PDF from filters at '{out_json}'")

        case "allids":
            if len(sys.argv) == 2:
                print("ERROR: please provide output txt to export ids to.")
                print("Try rerunning this command with the 'help' flag for more info.")
                sys.exit(1)

            out_txt: str = sys.argv[2]
            export_all_qids(q_infos, sys.argv[2])
            print(f"Complete! Exported ids to '{out_txt}'")

        case "skilltree":
            out_json: str = "skill-tree.json"
            gen_skill_tree(q_infos, out_json)
            print(f"Complete! Exported skill tree to '{out_json}'")

        case "derive-answers-from-qpdf":
            pdf_path = "./stand-engl-conv-exam.pdf"
            out_path = "./stand-engl-conv-exam-w-ans.pdf"
            # q_infos: list[QInfo] = import_q_parsed_info("./all-q-parsed.csv")
            q_infos: list[QInfo] = prepare.parse_question_pdf(pdf_path, False)

            ans_list: list[tuple[str, str]] = []
            for chosen in q_infos:
                for a_info in a_infos:
                    if a_info.q_id == chosen.q_id:
                        ans_list.append((a_info.q_id, a_info.answer))

            doc = Document()
            put_answers_on_page(doc, ans_list)
            doc.save(out_path)

        case "custom":
            # The information about the question set's composition is found from the json
            with open("input.json", "r") as f:
                input_json = json.load(f)

            incl_ans_key = input_json["includeAnsKey"]
            assert isinstance(incl_ans_key, bool)

            with open("input.json", "r") as f:
                input_json = json.load(f)

            create_question_set_w_diff(input_json, q_infos, a_infos if incl_ans_key else [], {
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
