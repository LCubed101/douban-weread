# V1.2 next integration slice

Do not connect Movie/TV to Feishu until the local smoke command confirms both read-only resolution and one explicit verified 想看 write with the user's own Douban session.

After that validation, the next PR should add:

- Film/TV mention extraction from the existing OCR/text capture path.
- Compact ambiguous candidate selection using title, year, media type, and director.
- One selection = one confirmation = direct `想看` write.
- Mixed Book + Film/TV routing in one capture without duplicating messages.
