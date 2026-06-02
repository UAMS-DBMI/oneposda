/*
	Some files missing the for_uid in the structure set sequence
	could not be parsed becuase of this constraint, so it was removed
*/
ALTER TABLE roi ALTER COLUMN for_uid DROP NOT NULL;
