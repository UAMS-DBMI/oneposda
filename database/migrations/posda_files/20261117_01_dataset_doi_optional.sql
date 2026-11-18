-- Make the dataset DOI optional.
--
-- A dataset can enter the release module before its DOI has been minted, and
-- nothing downstream reads this column (the IDC manifest takes the DOI from
-- WordPress). The UI hides the field for now; existing values are kept. The
-- unique constraint stays: Postgres allows any number of NULLs under it.
--
-- No BEGIN/COMMIT -- ./migrate wraps each migration in --single-transaction.

ALTER TABLE "public".dataset ALTER COLUMN dataset_doi DROP NOT NULL;
