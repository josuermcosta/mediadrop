drop table view_check;
CREATE TABLE view_check(
  view_id int(11) NOT NULL AUTO_INCREMENT,
  media_id int(11) NOT NULL,
  csrftoken char(80) NOT NULL,
  validated boolean NOT NULL,
  updated_date DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY(view_id),
  CONSTRAINT view_ibfk_1 FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE INDEX view_index_id ON view_check (media_id);
CREATE INDEX view_index_csrf ON view_check (csrftoken);

DROP EVENT reset_views;
CREATE EVENT reset_views
ON SCHEDULE EVERY 10 MINUTE
DO
DELETE FROM view_check WHERE updated_date < (CURRENT_TIMESTAMP - INTERVAL 1 HOUR);



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


DROP EVENT update_media_views;
CREATE EVENT update_media_views
ON SCHEDULE EVERY 3 HOUR
DO
update media SET views24 = views21, views21 = views18, views18 = views15, views15 = views12, views12 = views9, views9 = views6, views6 = views3, views3 = 0;

