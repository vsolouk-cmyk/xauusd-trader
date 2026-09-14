# Author completion checklist

Edit `author_metadata.tex` and `data_code_availability.txt` only for the remaining submission metadata, then rebuild every PDF.

- Name, academic title, university email, affiliation, postal address, city, postcode, and country were entered from the author's written instructions dated 5 September 2026.
- Add an ORCID and public profile URL only if the author supplies them; neither is required to remain as a placeholder.
- Insert the final public GitHub URL and immutable commit SHA after synchronization.
- Copy the same final repository URL and commit into `data_code_availability.txt`.
- Confirm or replace the funding statement.
- Confirm or replace the competing-interest statement.
- Confirm that the CRediT roles accurately describe every human author's work.
- If there is more than one author, add every author to the CAS front matter, title page, cover letter, and CRediT statement. Do not infer authorship from project participation.
- Confirm that the paper is not under consideration elsewhere and has been approved by every listed author.
- Confirm that third-party raw data may not be redistributed; revise the availability statement if licenses permit release.
- Recheck the journal's live submission fields immediately before upload because platform requirements can change.
- Select the subscription publication route unless a separately funded open-access decision is made; do not select the USD 3,590 open-access option by mistake.

Rebuild command:

```bash
./build_all.sh
```
