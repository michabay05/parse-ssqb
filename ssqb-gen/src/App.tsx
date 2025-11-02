import { useEffect, useState } from "react";

interface FilterCompProps {
    name: string;
    enabled: boolean;
    btnCallback: () => void;
    inputCallback: (qty: number) => void;
    qty: number;
}

function DomainFilterLine({ name, enabled, btnCallback, inputCallback, qty }: FilterCompProps) {
    const dropdownClass = "mr-2 hover:bg-gray-200 hover:cursor-pointer";
    // return <div className="flex border-t border-t-gray-700">
    return <div className="flex justify-between px-4">
        <div className="flex">
            <button onClick={btnCallback} className={dropdownClass}>
                <RightChevronSVG classNames={enabled ? "rotate-90": ""}/>
            </button>
            <h3>{name}</h3>
        </div>
        <input
            type="number"
            value={qty}
            className={`w-10 border-2 rounded-sm text-center px-1 ${enabled ? "hidden": "" }`}
            onChange={e => {
                const val = Number.parseInt(e.target.value);
                if (!isNaN(val)) {
                    inputCallback(val);
                } else {
                    alert("Only type numbers into the input boxes");
                }
            }}
        />
    </div>;
}

function SkillFilterLine({ name, enabled, btnCallback, inputCallback, qty }: FilterCompProps) {
    const addCancelBtnClass = "mr-2 hover:bg-gray-200 hover:cursor-pointer";
    const modifyBtn = enabled
        ? <CancelCircleSVG classNames={`text-red-400 ${addCancelBtnClass}`} />
        : <AddCircleSVG classNames={`text-green-600 ${addCancelBtnClass}`} />
    const skillEnabledClass = enabled ? "" : "bg-gray-300"

    return <div
        className={
            `flex w-11/12 ml-auto py-2 justify-between px-4 my-1 rounded-lg ${skillEnabledClass}`
        }>
        <div className="flex">
            <button onClick={btnCallback}>
                {modifyBtn}
            </button>
            <p>{name}</p>
        </div>
        <input
            type="number"
            value={qty}
            className={`w-10 border-2 rounded-sm text-center px-1 ${enabled ? "" : "hidden"}`}
            onChange={e => {
                const value = e.target.value;
                const numVal = Number.parseInt(value);
                if (!isNaN(numVal)) {
                    inputCallback(numVal);
                } else {
                    if (value.length > 0) alert("Only type numbers into the input boxes");
                }
            }}
        />
    </div>;
}

interface DictStrNum {
    [key: string]: number;
}

interface NestedDict {
    [key: string]: DictStrNum
}

interface SkillFilter {
    id: number;
    name: string;
    enabled: boolean;
    qty: number;
}

interface ExportData {
    outputPath: string;
    totalQuestions: number;
    RW: NestedDict;
    Math: NestedDict;
}

class DomainFilter {
    isRW: boolean;
    name: string;
    skills: SkillFilter[];
    enabled: boolean;
    qty: number;

    constructor(name: string, isRW: boolean, skills: SkillFilter[]) {
        this.name = name;
        this.enabled = false;
        this.isRW = isRW;
        this.skills = skills;
        this.qty = 0;
    }

    public setQty(newQty: number): void {
        this.qty = Math.floor(newQty);
    }

    public recomputeQty(): void {
        this.qty = 0;
        for (const skill of this.skills) {
            if (skill.enabled) this.qty += skill.qty;
        }
    }
}

function renderDomainFilters(dfs: DomainFilter[],
    domainBtnCallback: (domainName: string) => void,
    skillBtnCallback: (domainName: string, skillIndex: number) => void,
    domainInputCallback: (domainName: string, qty: number) => void,
    skillInputCallback: (domainName: string, skillIndex: number, qty: number) => void) {
    const output = [];
    for (const [dI, df] of dfs.entries()) {
        const skillFilters = [];
        if (df.enabled) {
            for (const [sI, skill] of df.skills.entries()) {
                skillFilters.push(
                    <SkillFilterLine
                        key={`${dI},${sI}`}
                        name={skill.name} enabled={skill.enabled}
                        qty={skill.qty}
                        btnCallback={() => {
                            skillBtnCallback(df.name, sI);
                        }}
                        inputCallback={qty => skillInputCallback(df.name, sI, qty)}
                    />
                )
            }
        }

        output.push(<div key={dI} className="py-4">
            <DomainFilterLine
                name={df.name} enabled={df.enabled}
                qty={df.qty}
                btnCallback={() => domainBtnCallback(df.name)}
                inputCallback={qty => domainInputCallback(df.name, qty)}
            />
            {skillFilters}
        </div>);
    }

    return <>{output}</>;
}

export default function App() {
    const [filters, setFilters] = useState<DomainFilter[]>([]);
    const [outputPath, setOutputPath] = useState<string>("");
    const [exportContent, setExportContent] = useState<string>("");

    const rw = "Reading and Writing";
    const math = "Math";
    useEffect(() => {
        let rwTree: NestedDict = {};
        let mathTree: NestedDict = {};
        const fetchSkillTree = async () => {
            const response = await fetch("skill-tree.json");
            const resJson = await response.json();
            rwTree = resJson[rw];
            mathTree = resJson[math];

            let i = 0;
            const tempFilters = [];
            for (const domain in rwTree) {
                const skills: SkillFilter[] = [];
                for (const skill in rwTree[domain]) {
                    skills.push({
                        id: i++,
                        name: skill,
                        enabled: false,
                        qty: 0,
                    });
                }
                tempFilters.push(new DomainFilter(domain, true, skills));
            }

            for (const domain in mathTree) {
                const skills: SkillFilter[] = [];
                for (const skill in mathTree[domain]) {
                    skills.push({
                        id: i++,
                        name: skill,
                        enabled: false,
                        qty: 0,
                    });
                }
                tempFilters.push(new DomainFilter(domain, false, skills));
            }

            setFilters(tempFilters);
        };
        fetchSkillTree();
    }, []);

    const skillBtnCallback = (domainName: string, skillIndex: number) => {
        setFilters(filters.map(df => {
            if (df.name === domainName) {
                // Toggle (enable/disable)
                df.skills[skillIndex].enabled = !df.skills[skillIndex].enabled;
                return df;
            } else {
                return df;
            }
        }))
    }

    const domainBtnCallback = (domainName: string) => {
        setFilters(filters.map(df => {
            if (df.name === domainName) {
                // Toggle (enable/disable)
                df.enabled = !df.enabled;
                df.recomputeQty();
                return df;
            } else {
                return df;
            }
        }))
    }

    const skillInputCallback = (domainName: string, skillIndex: number, qty: number) => {
        setFilters(filters.map(df => {
            if (df.name === domainName) {
                df.skills[skillIndex].qty = qty;
                df.recomputeQty();
                return df;
            } else {
                return df;
            }
        }))
    };

    const domainInputCallback = (domainName: string, qty: number) => {
        setFilters(filters.map(df => {
            if (df.name === domainName) {
                df.setQty(qty);
                return df;
            } else {
                return df;
            }
        }))
    };

    const exportBtnCallback = () => {
        if (outputPath.length == 0) {
            alert("Please type output path for the pdf.");
            return;
        }

        let path: string = "";
        if (outputPath.endsWith(".pdf")) {
            path = outputPath.trim();
        } else {
            path = `${outputPath.trim()}.pdf`;
        }

        // TODO: add some parsing to ensure that the pdf names are valid names
        const exportData: ExportData = {
            "outputPath": path,
            "totalQuestions": 0,
            "RW": {},
            "Math": {},
        };

        for (const df of filters) {
            if (df.qty === 0) continue;
            const info: DictStrNum = {};

            if (df.enabled) {
                df.recomputeQty();
                df.skills.filter(s => s.enabled).forEach(s => {
                    info[s.name] = s.qty;
                });
            } else {
                const len = df.skills.length;
                const total = df.qty;
                const qPerSkill = Math.floor(total / len);
                df.skills.forEach((s, i) => {
                    if (i < len - 1) {
                        info[s.name] = qPerSkill;
                    } else {
                        info[s.name] = total - i * qPerSkill;
                    }
                });
            }

            if (df.isRW) {
                exportData["RW"][df.name] = info;
            } else {
                exportData["Math"][df.name] = info;
            }
            exportData["totalQuestions"] += df.qty;
        }
        setExportContent(JSON.stringify(exportData, null, 4));
    };

    return <div className="w-9/10 max-w-5xl mx-auto">
        <div className="grid grid-cols-2 grid-rows-[fit-content(100%)_fit-content(100%)] justify-around">
            <div className="w-full p-5">
                <h2 className="text-center font-bold mb-4">{rw}</h2>
                {renderDomainFilters(
                    filters.filter(f => f.isRW),
                    domainBtnCallback, skillBtnCallback,
                    domainInputCallback, skillInputCallback
                )}
            </div>
            <div className="w-full p-5">
                <h2 className="text-center font-bold mb-4">{math}</h2>
                {renderDomainFilters(
                    filters.filter(f => !f.isRW),
                    domainBtnCallback, skillBtnCallback,
                    domainInputCallback, skillInputCallback
                )}
            </div>
            <div className="my-3 flex h-fit justify-between col-span-2">
                <div className="flex flex-1">
                    <p className="w-fit">Output PDF filename:</p>
                    <input
                    type="text"
                    onChange={e => setOutputPath(e.target.value) }
                    className="px-4 mx-6 border-2 rounded-lg flex-1"
                    />
                </div>
                <button
                    onClick={exportBtnCallback}
                    className="py-2 px-6 rounded-lg hover:cursor-pointer bg-blue-900 text-white">Export</button>
            </div>
        </div>

        {
            exportContent.length > 0
            ? <div className="mt-6">
                <p className="mb-4">
                    Copy the JSON text below and save it in the project folder as <code className="bg-gray-300 rounded">input.json</code>.
                </p>
                <div className="bg-zinc-300 rounded-lg relative">
                    <button
                        onClick={() => navigator.clipboard.writeText(exportContent)}
                        className="p-2 absolute top-6 right-8 hover:cursor-pointer hover:rounded hover:bg-zinc-400">
                        <ClipboardSVG />
                    </button>
                    <pre className="p-6 w-full">
                        {exportContent}
                    </pre>
                </div>
            </div>
            : <></>
        }
    </div>;
}

interface IconSVGProps {
    classNames?: string;
}

// Source: https://lucide.dev/icons/circle-x
function CancelCircleSVG({classNames}: IconSVGProps) {
    return <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
        className={classNames}>
        <circle cx="12" cy="12" r="10" />
        <path d="m15 9-6 6" />
        <path d="m9 9 6 6" />
    </svg>;
}

// Source: https://lucide.dev/icons/circle-plus
function AddCircleSVG({classNames}: IconSVGProps) {
    return <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
        className={classNames}>
        <circle cx="12" cy="12" r="10" />
        <path d="M8 12h8" />
        <path d="M12 8v8" />
    </svg>;
}

// Source: https://lucide.dev/icons/chevron-right
function RightChevronSVG({classNames}: IconSVGProps) {
    return <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
        className={classNames}>
        <path d="m9 18 6-6-6-6"/>
    </svg>
}

// Source: https://lucide.dev/icons/clipboard
function ClipboardSVG() {
    return <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
        className="">
        <rect width="8" height="4" x="8" y="2" rx="1" ry="1"/>
        <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>
    </svg>
}
