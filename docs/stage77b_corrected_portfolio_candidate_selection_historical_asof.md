# Stage77B Corrected Portfolio Candidate Selection Historical-As-Of

Stage77B corrects the Stage77 false `S77_NO_VALID_ANCHOR` result.

The correction is narrow:
- evaluate only known candidate rules;
- count missing data only over trigger/date/price columns;
- do not treat pending or non-trigger rows as feature failures;
- select at most a small portfolio anchored by K06.

No order authorization is provided.
