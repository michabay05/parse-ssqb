import cors from "cors";
import express from "express";
import fs from "node:fs";
import { exec } from "node:child_process";


const app = express();
const port = 8080;

// Allow cross-origin resource sharing (CORS)
app.use(cors());
app.use(express.json());

let pdfOutputPath = "";

app.post("/filter-req", (req, res) => {
    if (req.body === undefined) {
        console.log("request body is undefined.");
        res.status(400).send("Request body was undefined");
        return;
    }

    const jsonStr = JSON.stringify(req.body, null, 4);
    fs.writeFileSync("../input.json", jsonStr);

    pdfOutputPath = req.body["outputPath"];

    exec(
        "uv run main.py qset input.json",
        { cwd: "../" },
        (error, stdout, stderr) => {
            if (error) {
                console.error("Error:", error);
                return;
            }
            if (stderr) {
                console.error("Stderr:", stderr);
                return;
            }
            console.log("Stdout:", stdout);
            console.log("backend: Ran cmd")
            res.status(200).send("Successful submitted JSON instructions");
        }
    );
});

app.get("/download", (req, res) => {
    res.download(`../${pdfOutputPath}`);
    res.status(200);
});

app.get("/all-ids", (req, res) => {
    exec(
        "uv run main.py allids qids.json",
        { cwd: "../" },
        (error, stdout, stderr) => {
            if (error) {
                console.error("Error:", error);
                return;
            }
            if (stderr) {
                console.error("Stderr:", stderr);
                return;
            }
            console.log("Stdout:", stdout);
            console.log("backend: Ran cmd")
        }
    );

    res.sendFile("qids.json", { root: ".." });
    res.status(200);
})

app.listen(port, () => {
    console.log(`Example app listening at http://localhost:${port}`);
});
