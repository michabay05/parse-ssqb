import { useEffect, useState } from "react";

interface FilterCompProps {
    name: string;
    enabled: boolean;
    btnCallback: () => void;
}

function FilterLine({ name, enabled, btnCallback }: FilterCompProps) {
    const addCancelBtnClass = "mr-2 hover:bg-gray-200 hover:cursor-pointer";
    const modifyBtn = enabled
        ? <CancelCircleSVG classNames={`text-red-400 ${addCancelBtnClass}`} />
        : <AddCircleSVG classNames={`text-green-600 ${addCancelBtnClass}`} />

    return <div
        className="flex w-11/12 ml-auto py-2 justify-between border-b border-b-gray-600">
        <div className="flex">
            <button onClick={btnCallback}>
                {modifyBtn}
                {/*<CancelCircleSVG classNames={`text-red-400 ${addCancelBtnClass} ${enabled ? "" : "hidden"}`} />
                <AddCircleSVG classNames={`text-green-600 ${addCancelBtnClass} ${enabled ? "hidden" : ""}`} />*/}
            </button>
            <p>{name}</p>
        </div>
        <input type="number" className="w-10 border-2 rounded-sm text-center px-1" pattern="[0-9]" />
    </div>;
}

interface NestedDict {
    [key: string]: {
        [key: string]: number;
    }
}

interface SkillFilter {
    id: number;
    name: string;
    enabled: boolean;
    qty: number;
}

class DomainFilter {
    isRW: boolean;
    name: string;
    skills: SkillFilter[];

    constructor(name: string, isRW: boolean, skills: SkillFilter[]) {
        this.name = name;
        this.isRW = isRW;
        this.skills = skills;
    }
}

function renderDomainFilters(dfs: DomainFilter[], btnCallback: (domainName: string, skillIndex: number) => void) {
    const output = [];
    for (const [dI, df] of dfs.entries()) {
        const skillFilters = [];
        for (const [sI, skill] of df.skills.entries()) {
            skillFilters.push(
                <FilterLine
                    key={`${dI},${sI}`}
                    name={skill.name} enabled={skill.enabled}
                    btnCallback={() => {
                        btnCallback(df.name, sI);
                    }}
                />
            )
        }

        output.push(<div key={dI} >
            <h3>{df.name}</h3>
            {skillFilters}
        </div>);
    }

    return <>{output}</>;
}

export default function App() {
    const [filters, setFilters] = useState<DomainFilter[]>([]);

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

    const btnCallback = (domainName: string, skillIndex: number) => {
        setFilters(filters.map(f => {
            if (f.name == domainName) {
                // Toggle (enable/disable)
                const newSkills = [...f.skills];
                const v = newSkills[skillIndex].enabled;
                newSkills[skillIndex].enabled = !v;
                const newDomain = new DomainFilter(domainName, f.isRW, newSkills);
                return newDomain;
            } else {
                return f;
            }
        }))
    }


    return <div className="flex w-9/10 max-w-5xl mx-auto justify-around">
        <div className="w-full outline p-5">
            <h2 className="text-center font-bold mb-4">{rw}</h2>
            {renderDomainFilters(filters.filter(f => f.isRW), btnCallback)}
        </div>
        <div className="w-full outline p-5">
            <h2 className="text-center font-bold mb-4">{math}</h2>
            {renderDomainFilters(filters.filter(f => !f.isRW), btnCallback)}
        </div>
    </div>;
}

interface IconSVGProps {
    classNames: string;
}

function CancelCircleSVG({classNames}: IconSVGProps) {
    return <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
        className={classNames}>
        <circle cx="12" cy="12" r="10" />
        <path d="m15 9-6 6" />
        <path d="m9 9 6 6" />
    </svg>;
}

function AddCircleSVG({classNames}: IconSVGProps) {
    return <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
        className={classNames}>
        <circle cx="12" cy="12" r="10" />
        <path d="M8 12h8" />
        <path d="M12 8v8" />
    </svg>;
}
