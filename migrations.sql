DROP EVENT update_media_views;

ALTER TABLE media
DROP viewsN;

ALTER TABLE media
ADD views3 INT DEFAULT 0,
ADD views6 INT DEFAULT 0,
ADD views9 INT DEFAULT 0,
ADD views12 INT DEFAULT 0,
ADD views15 INT DEFAULT 0,
ADD views18 INT DEFAULT 0,
ADD views21 INT DEFAULT 0,
ADD views24 INT DEFAULT 0;

update media
SET views3 = 0,
views6 = 0,
views9 = 0,
views12 = 0,
views15 = 0,
views18 = 0,
views21 = 0,
views24 = 0;


CREATE EVENT update_media_views
ON SCHEDULE EVERY 3 HOUR
DO
update media SET views24 = views21, views21 = views18, views18 = views15, views15 = views12, views12 = views9, views9 = views6, views6 = views3, views3 = 0;