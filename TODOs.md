# TODOs
Below are all the list of TODOs created by @michabay05.

## Future TODOs
- [ ] (feat) Import parsed information into memory
- [ ] (feat) Create a way to verify that each question has a unique id
    - So far, that is just an implicit assumption
- [ ] (feat) Add REPL to interact with and has the following features
    - [ ] Filtering
    - [ ] Question organizations (r&w hard random, math easy random, math hard 1,2,4,23)
    - [ ] Any combination of questions
- [ ] (feat) Maintain a list of mupdf objects for each object
    - Ideally, there should only be one object for one PDF
- [ ] (refactor) Find a better way of detecting empty pages
    - As of right now, I have tried to check if a page is empty by checking if it has text, image, or drawings.
      However, that has not work exactly so I am going to just focus on text and images.

## v0.1
- [x] (feat) Identify a mechanism to identify the page ranges of a question
    - Some questions take up more than one page.
- [x] (fix) Resolve parsing issue with R&W pdfs
- [x] (feat) Export parsed information to csv using pandas dataframe
- [x] (fix) Identify and remove duplications of the same questions
    - [x] Detect duplicates
    - [x] Remove duplicates
    - [x] Save a dedupliated version of the pdf
