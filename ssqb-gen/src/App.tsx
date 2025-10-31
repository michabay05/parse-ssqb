import { useEffect, useState } from "react";

interface FilterCompProps {
    name: string;
    isSkill: boolean;
}

function FilterLine({ name, isSkill }: FilterCompProps) {
    const text = isSkill ? <p>{name}</p> : <h3>{name}</h3>
    const skillClasses = isSkill ? "w-11/12 ml-auto py-2" : "pt-4 pb-2";
    const addCancelBtnClass = "mr-2 text-green-600 hover:bg-gray-200 hover:cursor-pointer";

    return <div className={`flex ${skillClasses} justify-between border-b border-b-gray-600`}>
        {/* Left side */}
        <div className="flex">
            {/*<input type="checkbox" className="mr-4" />*/}
            <button>
                <AddCircleSVG classNames={addCancelBtnClass} />
            </button>
            {text}
        </div>
        {/* Right side */}
        <div>
            {/*<RandomDiceSVG classNames="" />*/}
            <input type="number" className="w-10 border-2 rounded-sm text-center px-1" pattern="[0-9]" />
        </div>
    </div>;
}

interface NestedDict {
    [key: string]: {
        [key: string]: number;
    }
}

export default function App() {
    const [rwTree, setRWTree] = useState<NestedDict>({});
    const [mathTree, setMathTree] = useState<NestedDict>({});
    const rw = "Reading and Writing";
    const math = "Math";
    useEffect(() => {
        const fetchSkillTree = async () => {
            const response = await fetch("skill-tree.json");
            const resJson = await response.json();
            setRWTree(resJson[rw]);
            setMathTree(resJson[math]);
        };

        fetchSkillTree();
    }, []);


    const rwFilters = [];
    for (const domain in rwTree) {
        rwFilters.push(<FilterLine name={domain} isSkill={false} />)
        for (const skill in mathTree) {
            rwFilters.push(<FilterLine name={skill} isSkill={true} />)
        }
    }

    const mathFilters = [];
    for (const domain in mathTree) {
        mathFilters.push(<FilterLine name={domain} isSkill={false} />)
        for (const skill in mathTree[domain]) {
            mathFilters.push(<FilterLine name={skill} isSkill={true} />)
        }
    }

    return <div className="flex w-9/10 max-w-5xl mx-auto justify-around">
        <div className="w-full outline p-5">
            <h2 className="text-center font-bold mb-4">{rw}</h2>
            {rwFilters}
        </div>
        <div className="w-full outline p-5">
            <h2 className="text-center font-bold mb-4">{math}</h2>
            {mathFilters}
        </div>
    </div>;
}

// Source: https://lucide.dev/icons/dices
function RandomDiceSVG() {
    return <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
        className="">
        <rect width="12" height="12" x="2" y="10" rx="2" ry="2" />
        <path d="m17.92 14 3.5-3.5a2.24 2.24 0 0 0 0-3l-5-4.92a2.24 2.24 0 0 0-3 0L10 6" />
        <path d="M6 18h.01" />
        <path d="M10 14h.01" />
        <path d="M15 6h.01" />
        <path d="M18 9h.01" />
    </svg>;
}

function CancelCircleSVG() {
    return <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
        className="">
        <circle cx="12" cy="12" r="10" />
        <path d="m15 9-6 6" />
        <path d="m9 9 6 6" />
    </svg>;
}

interface IconSVGProps {
    classNames: string;
}

function AddCircleSVG({classNames}: IconSVGProps) {
    return <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
        className={classNames}>
        <circle cx="12" cy="12" r="10" />
        <path d="M8 12h8" />
        <path d="M12 8v8" />
    </svg>;
}
