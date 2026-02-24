from pathlib import Path
from typing import Literal
import json, math, os, random, re, sys

import fitz
from pymupdf import Document
import pandas as pd
import numpy as np

import prepare
from prepare import AnsInfo, Level, QInfo

Subject = Literal["Reading and Writing", "Math"]

class QGeneration:
    def __init__(self,
        q_parsed_path: str = "./all-q-parsed.csv", a_parsed_path: str = "./all-a-parsed.csv"
    ) -> None:
        try:
            self.q_infos: list[QInfo] = prepare.import_q_parsed_info(q_parsed_path)
        except:
            print(f"ERROR: Could not find {q_parsed_path}; question information loading failed...")
            print("WARN: Either regenerate the parsed csv or find the parsed csv path")

        try:
            self.a_infos: list[AnsInfo] = prepare.import_a_parsed_info(a_parsed_path)
        except:
            print(f"ERROR: Could not find {a_parsed_path}; answer information loading failed...")
            print("WARN: Either regenerate the parsed csv or find the parsed csv path")

        self.qdf: pd.DataFrame = prepare.q_infos_to_df(self.q_infos)

    def parse_pdfs(self,
        q_out_csv: str = "all-q-parsed.csv", a_out_csv: str = "all-a-parsed.csv"
    ) -> None:
        file_paths: list[tuple[str, bool]] = []
        for dir_ind, dir in enumerate(["./alls/questions/", "./excludeds/questions/"]):
            for aqp in os.listdir(dir):
                p = Path(dir) / aqp
                file_paths.append((str(p), dir_ind == 1))

        prepare.parse_all_q_pdfs(file_paths, q_out_csv)
        print(f"Complete! Exported question PDFs info to '{q_out_csv}'")

        file_paths = []
        for dir_ind, dir in enumerate(["./alls/answers/", "./excludeds/answers/"]):
            for aqp in os.listdir(dir):
                p = Path(dir) / aqp
                file_paths.append((str(p), dir_ind == 1))

        prepare.parse_all_a_pdfs(file_paths, a_out_csv)
        print(f"Complete! Exported answer PDFs info to '{a_out_csv}'")

    def gen_skill_tree(self, output_json: str, w_difficulty: bool = False) -> None:
        tree: dict[str, dict[str, dict]] = {}
        for info in self.q_infos:
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

                # NOTE: What an annoying bug. Can CollegeBoard really not make sure that they use a consistent naming mechanism? I guess it's not suprising...
                if skill == "Cross-text Connections":
                    skill = "Cross-Text Connections"

                if skill not in tree[info.test][info.domain]:
                    tree[info.test][info.domain][skill] = 0

                tree[info.test][info.domain][skill] += 1

        with open(output_json, "w") as f:
            json.dump(tree, f, indent=4)

    def put_answers_on_page(self, doc: Document, answers: list[tuple[str, str]]) -> None:
        dpi = 72
        paper_w, paper_h = (8.5, 11)
        width, height = (paper_w*dpi, paper_h*dpi)
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

    def create_question_set_v2(self, input: dict, shuffle: bool = True,
        incl_ans_temp: bool = True, incl_ans_key: bool = True,
        exclude_excludeds: bool = True
    ) -> list[QInfo]:
        rw_possible_df = self.gather_possible_set("Reading and Writing", input)
        math_possible_df = self.gather_possible_set("Math", input)

        # Add column for weight (based on difficulty)
        prob_dict: dict[Level, float] = input["prob"]
        new_qdf = pd.concat([rw_possible_df, math_possible_df], ignore_index=True)
        if exclude_excludeds:
            new_qdf = new_qdf[new_qdf["Excluded"] == False]

        new_qdf["rand_wt"] = np.zeros(len(new_qdf), dtype=np.float64)
        print(prob_dict)
        for dif, prob in prob_dict.items():
            print(dif, prob)
            new_qdf.loc[new_qdf["Difficulty"] == dif, "rand_wt"] = prob

        # NOTE: I know this terrible but it will do for now.
        # TODO: Refactor this (at some point...)
        # NOTE: Potential solution to this is to change the filter file format into
        # something where info is stored in flat-style (i.e. no nesting): like .csv
        # For instance:
        #     Test, Math, 45
        #     Domain, Craft and Structure, 10
        #     Skill, Words in Context, 12
        #     ...

        chosen_ids: list[str] = []
        debug_df = pd.DataFrame(columns=self.qdf.columns)

        # Shorter alias: new_qdf <=> df
        df = new_qdf
        for subject in ["Reading and Writing", "Math"]:
            subject_filter: int | dict = input[subject]
            if isinstance(subject_filter, int):
                filtered = df[df["Test"] == subject]
                f_rows = filtered.sample(
                    n=subject_filter, weights="rand_wt", replace=False)
                debug_df = pd.concat([debug_df, f_rows], ignore_index=True)

                chosen_ids.extend(f_rows["ID"])

            elif isinstance(subject_filter, dict):
                for domain, dom_filter in subject_filter.items():
                    if isinstance(dom_filter, int):
                        filtered = df[df["Domain"] == domain]
                        f_rows = filtered.sample(
                            n=dom_filter, weights="rand_wt", replace=False)
                        debug_df = pd.concat([debug_df, f_rows], ignore_index=True)

                        chosen_ids.extend(f_rows["ID"])
                    elif isinstance(dom_filter, dict):

                        for skill, sk_filter in dom_filter.items():
                            if isinstance(sk_filter, int):
                                filtered = df[df["Skill"] == skill]
                                f_rows = filtered.sample(
                                    n=sk_filter, weights="rand_wt", replace=False)
                                debug_df = pd.concat(
                                    [debug_df, f_rows], ignore_index=True)

                                chosen_ids.extend(f_rows["ID"])

        # Specific id filtering
        if "chosenIds" in input:
            specific_ids = input["chosenIds"]
            assert isinstance(specific_ids, list)
            chosen_ids.extend(specific_ids)

        chosen_set = list(set(chosen_ids))

        if shuffle:
            random.shuffle(chosen_set)

        with open("test.txt", "w") as f:
            print(debug_df.to_string(), file=f)

        # Convert from id strings to QInfo
        chosen_qs: list[QInfo] = []
        for q in self.q_infos:
            if q.excluded: continue
            for id in chosen_set:
                if id == q.q_id:
                    chosen_qs.append(q)
                    break

        doc: Document = self.gen_pdf_from_q_infos(chosen_qs)
        output_pdf_path: str = input["outputPath"]
        doc.save(output_pdf_path)

        if "includeAnsTemplate" in input:
            incl_ans_temp = input[incl_ans_temp]

        if incl_ans_temp:
            base_name: str = output_pdf_path.removesuffix(".pdf")
            ans_template_path: str = base_name + "-empty.csv"
            self.gen_answer_template(chosen_qs, ans_template_path)

        if "includeAnsKey" in input:
            incl_ans_key = input["includeAnsKey"]

        if incl_ans_key:
            base_name: str = output_pdf_path.removesuffix(".pdf")
            ans_list: list[tuple[str, str]] = []
            for chosen in chosen_qs:
                for a_info in self.a_infos:
                    if a_info.q_id == chosen.q_id:
                        ans_list.append((a_info.q_id, a_info.answer))

            # self.put_answers_on_page(doc, ans_list)
            self.export_answer_csv(ans_list, base_name + "-key.csv")

        return []

    def gather_possible_set(self, subject: str, input: dict) -> pd.DataFrame:
        # NOTE: Backward compability ("Reading and Writing" used to written as "RW")
        if subject == "RW": subject = "Reading and Writing"

        # Columns of self.qdf
        # ID, Pages, Difficulty, Excluded, Test, Domain, Skill, Source_PDF,

        df = self.qdf

        subject_filter: int | dict = input[subject]
        if isinstance(subject_filter, int):
            return df[df["Test"] == subject]

        if not isinstance(subject_filter, dict):
            raise TypeError(
                f"Unknown type for the subject filter: {type(subject_filter)}")

        new_qdf: pd.DataFrame = pd.DataFrame(columns=df.columns)
        for domain, dom_filter in subject_filter.items():
            if isinstance(dom_filter, int):
                new_qdf = pd.concat([new_qdf, df[df["Domain"] == domain]])
            elif isinstance(dom_filter, dict):

                for skill, sk_filter in dom_filter.items():
                    if isinstance(sk_filter, int):
                        new_qdf = pd.concat([new_qdf,
                            df[(df["Domain"] == domain) & (df["Skill"] == skill)]
                        ])
                    else:
                        raise TypeError(
                            f"Unknown type for the skill filter: {type(sk_filter)}")

            else:
                raise TypeError(
                    f"Unknown type for the domain filter: {type(dom_filter)}")

        return new_qdf

    def create_question_set(self, input_json: dict, shuffle: bool = True) -> None:
        print("Using a deprecated function: create_question_set()")

        output_pdf_path: str = input_json["outputPath"]
        requested_count: int = input_json["totalQuestions"]
        specific_ids: list[str] = input_json["chosenIds"]
        prob: dict[Level, float] = input_json["prob"]
        incl_ans_key: bool = input_json["includeAnsKey"]
        incl_ans_temp: bool = input_json["includeAnsTemplate"]

        qs_by_diff: dict[Level, list[int]] = {
            "easy": [],
            "medium": [],
            "hard": []
        }

        # Subject based filtering
        for test in ["RW", "Math"]:
            for domain, skills_info in input_json[test].items():
                for skill in skills_info.keys():
                    # Find questions that test the expected skill
                    for i, q in enumerate(self.q_infos):
                        if q.excluded: continue
                        if q.domain == domain and q.skill == skill:
                            qs_by_diff[q.level].append(i)

        all_chosen: list[QInfo] = []
        # TOTAL = RANDOM_REQUESTED + SPECIFIC_ID_REQUESTED
        max_random_q_count = requested_count - len(specific_ids)
        if prob:
            assert prob["easy"] + prob["medium"] + prob["hard"] == 1.0

            for diff, q_inds in qs_by_diff.items():
                # NOTE: Ensure that there is at least one question of a given difficulty
                n = max(int(max_random_q_count * prob[diff]), 1)
                all_chosen.extend([self.q_infos[ind] for ind in random.sample(q_inds, n)])
        else:
            # Flatten the dictionary's values into a 1D list
            all_valids = []
            for q_inds in qs_by_diff.values():
                all_valids.extend(q_inds)

            all_chosen.extend([
                self.q_infos[c_i] for c_i in random.sample(all_valids, max_random_q_count)
            ])

        # NOTE: The expectation is that the random selection process produces N or more questions
        # where N = the maximum number of questions that can be randomly generated. The rest of the
        # questions are from specific ids.
        assert len(all_chosen) >= max_random_q_count, (
            f"[len(all_chosen) = {len(all_chosen)}] < [{max_random_q_count} = max_random_q_count]"
        )

        # Specific id filtering
        if len(specific_ids) > 0:
            all_chosen_so_far = [chosen.q_id for chosen in all_chosen]
            for q_info in self.q_infos:
                if (q_info.q_id in specific_ids) and (q_info.q_id not in all_chosen_so_far):
                    all_chosen.append(q_info)

        assert len(all_chosen) <= requested_count, (
            f"Questions that satisfy reqs ({len(all_chosen)}) <= Requested questions ({requested_count}): False"
        )

        if shuffle:
            random.shuffle(all_chosen)

        doc: Document = self.gen_pdf_from_q_infos(all_chosen)
        doc.save(output_pdf_path)

        if incl_ans_temp:
            base_name: str = output_pdf_path.removesuffix(".pdf")
            ans_template_path: str = base_name + "-empty.csv"
            self.gen_answer_template(all_chosen, ans_template_path)

        if incl_ans_key:
            base_name: str = output_pdf_path.removesuffix(".pdf")
            ans_list: list[tuple[str, str]] = []
            for chosen in all_chosen:
                for a_info in self.a_infos:
                    if a_info.q_id == chosen.q_id:
                        ans_list.append((a_info.q_id, a_info.answer))

            # self.put_answers_on_page(doc, ans_list)
            self.export_answer_csv(ans_list, base_name + "-key.csv")

    # ans_list: (question_id, answer)
    def export_answer_csv(self, ans_list: list[tuple[str, str]], answers_csv_path: str) -> None:
        data: dict = {
            "No.": [],
            "Question ID": [],
            "Answers": []
        }
        for i, (q_id, answer) in enumerate(ans_list):
            data["No."].append(i + 1)
            data["Question ID"].append(f"\"{q_id}\"")
            data["Answers"].append(answer)

        pd.DataFrame(data).to_csv(answers_csv_path, index=False)

    def gen_answer_template(self, all_chosen: list[QInfo], ans_template_path: str) -> None:
        data: dict = {
            "No.": [],
            "Question ID": [],
            "Answers": []
        }
        for i, chosen in enumerate(all_chosen):
            data["No."].append(i + 1)
            data["Question ID"].append(f"'{chosen.q_id}'")
            data["Answers"].append("")

        pd.DataFrame(data).to_csv(ans_template_path, index=False)

    def check_answers(self, student_ans_path: str, ans_key_path: str) -> tuple[int, int]:
        res_df = pd.read_csv(student_ans_path)
        ans_df = pd.read_csv(ans_key_path)
        assert len(res_df) == len(ans_df), f"{len(res_df)} == {len(ans_df)}"

        id_col = "Question ID"
        ans_col = "Answers"

        # Sort the dataframes by the id cols
        res_df.sort_values(by=id_col, inplace=True)
        ans_df.sort_values(by=id_col, inplace=True)

        # NOTE: Convert from dataframe to pairs of id and answers
        responses: list[tuple[str, str]] = [
            (id, str(res)) for id, res in zip(res_df[id_col], res_df[ans_col])]
        answers: list[tuple[str, str]] = [
            (id, str(ans)) for id, ans in zip(ans_df[id_col], ans_df[ans_col])]
        assert len(responses) == len(answers)

        correct, total = 0, 0
        for i in range(len(responses)):
            r_id, res = responses[i]
            a_id, ans = answers[i]
            assert r_id == a_id, "ID mismatch after sorting by id"
            total += 1

            if res == "nan":
                # Found an unanswered question
                continue

            math_mode = any([ltr.isdigit() for ltr in ans])
            if not math_mode:
                # NOTE: Since it doesn't contain digits, just compare the strings
                correct += 1 if res == ans else 0
                continue

            if res == ans:
                # NOTE: Even though it contains digits, just compare the strings to see if it
                # matches. If it does not, proceed to math mode evaluation.
                correct += 1
                continue

            re_pat = r"([\d]+\/[\d]+)|([\d.]+)"
            # Regex match for response
            rm = re.findall(re_pat, res, re.MULTILINE)[0]
            # Regex match for answer
            am = re.findall(re_pat, ans, re.MULTILINE)[0]

            assert len(rm) == 2
            assert len(am) == 2

            # NOTE: Only one of these two (the fraction or decimal) should be matched
            assert len(rm[0]) == 0 or len(rm[1]) == 0
            assert len(am[0]) == 0 or len(am[1]) == 0

            # First, convert any fraction into a decimal value
            rmd, amd = 0.0, 0.0
            if len(rm[0]) > 0:
                nums = str(rm[0]).strip().split('/')
                rmd = float(nums[0]) / float(nums[1])
            else:
                rmd = float(rm[1])

            if len(am[0]) > 0:
                nums = str(am[0]).strip().split('/')
                amd = float(nums[0]) / float(nums[1])
            else:
                amd = float(am[1])

            correct += 1 if abs(rmd - amd) < 1e-3 else 0

        return (correct, total)

    def gen_pdf_from_q_infos(self, q_infos: list[QInfo]) -> Document:
        out_pdf: Document = Document()

        print(f"Saving {len(q_infos)} questions...")

        path_to_docs: dict[str, Document] = {}
        for ssqb in q_infos:
            if ssqb.src_pdf not in path_to_docs.keys():
                path_to_docs[ssqb.src_pdf] = fitz.open(ssqb.src_pdf)

            doc: Document = path_to_docs[ssqb.src_pdf]
            page_nos: list[int] = ssqb.pg_inds
            if len(page_nos) == 1:
                page_nos.append(page_nos[0])

            assert len(page_nos) <= 3, (
                f"A page range should have a max of 3 numbers -> pages: {page_nos}; src = '{ssqb.src_pdf}'"
            )

            for pg_no in range(page_nos[0], page_nos[1] + 1):
                if not prepare.is_page_empty(doc.load_page(pg_no)):
                    out_pdf.insert_pdf(doc, from_page=pg_no, to_page=pg_no)

        return out_pdf

    def derive_answers_from_qpdf(self,
        in_pdf_path: str, out_pdf_path: str, append_ans: bool = True
    ) -> None:
        q_infos: list[QInfo] = prepare.parse_question_pdf(in_pdf_path, False)

        ans_list: list[tuple[str, str]] = []
        for chosen in q_infos:
            for a_info in self.a_infos:
                if a_info.q_id == chosen.q_id:
                    ans_list.append((a_info.q_id, a_info.answer))

        doc = fitz.open(in_pdf_path) if append_ans else Document()
        qg.put_answers_on_page(doc, ans_list)
        doc.save(out_pdf_path)

    def export_all_qids(self, out_path: str = "qids.json") -> None:
        all_ids: list[str] = [ssqb.q_id for ssqb in self.q_infos]
        with open(out_path, "w") as f:
            json.dump({"qIds": all_ids}, f, indent=4)

        print(f"Complete! Exported ids to '{out_path}'")


def usage(program: str) -> None:
    print(f"USAGE: {program} <MODES> [ARGS]\n")
    print("Modes:")
    print("         qset < IN_JSON  >            |  Generate question set given an input json for filtering")
    print("       allids < OUT_JSON >            |  Get a json containing the id of all questions")
    print("     parse-qs < OUT_CSV  >            |  Categorize questions pdfs and output a single csv")
    print("     parse-as < OUT_CSV  >            |  Categorize answers pdfs and output a single csv")
    print("    skilltree                         |  Generate a skill tree with quantity; save into json")
    print("    regen-ans <  IN_PDF  > <OUT_PDF>  |  Regenerate answers from a question pdf")
    print("        grade <  IN_CSV  > <ANS_CSV>  |  Grade responses against answer csv")
    print("         help                         |  Get this help message")

if __name__ == "__main__":
    program: str = sys.argv[0]
    if len(sys.argv) == 1:
        usage(program)
        sys.exit(1)

    mode: str = sys.argv[1]
    args: list[str] = sys.argv[2:]
    qg = QGeneration()

    match mode:
        case "parse":
            qg.parse_pdfs()

        case "qset":
            input_path: str = args[0] if len(args) > 0 else "input.json"
            # The information about the question set's composition is found from the json
            with open(input_path, "r") as f:
                input_json = json.load(f)

            # qg.create_question_set(input_json)
            qg.create_question_set_v2(input_json)
            print(f"Complete! Exported PDF from filters at '{input_path}'")

        case "allids":
            qg.export_all_qids()

        case "skilltree":
            out_json: str = args[0] if len(args) > 0 else "skill-tree.json"
            qg.gen_skill_tree(out_json)
            print(f"Complete! Exported skill tree to '{out_json}'")

        case "regen-ans":
            if len(args) != 2:
                print("ERROR: provide input json to use for filtering.")
                print("Try rerunning this command with the 'help' flag for more info.")
                sys.exit(1)

            qg.derive_answers_from_qpdf(args[0], args[1])

        case "grade":
            if len(args) != 2:
                print("ERROR: provide response and answer csvs only.")
                print("Try rerunning this command with the 'help' flag for more info.")

            correct, total = qg.check_answers("sample-response2.csv", "sample-key.csv")
            print(correct, "out of", total)

        case "help":
            usage(program)

        case _:
            usage(program)
            print(f"\nERROR: Unknown mode: '{mode}'")
