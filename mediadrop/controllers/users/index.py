
from pylons import request

import webhelpers.paginate

from mediadrop.lib.auth import has_permission
from mediadrop.lib.base import BaseController
from mediadrop.lib.decorators import expose, observable
from mediadrop.model import Comment, Media
from mediadrop.plugin import events
import logging

log = logging.getLogger(__name__)

class IndexController(BaseController):
    """User dashboard actions"""

    @expose('users/index.html')
    @observable(events.Users.IndexController.index)
    def index(self, **kwargs):
        recent_media = Media.query.published()\
            .order_by(Media.publish_on.desc())[:5]

        return dict(
            review_page = self._fetch_page('awaiting_review'),
            encode_page = self._fetch_page('awaiting_encoding'),
            publish_page = self._fetch_page('awaiting_publishing'),
            recent_media = recent_media,
            comments = Comment.query,
        )

    @expose('users/media/dash-table.html')
    @observable(events.Admin.IndexController.media_table)
    def media_table(self, table, page, **kwargs):
        """Fetch XHTML to inject when the 'showmore' ajax action is clicked.

        :param table: ``awaiting_review``, ``awaiting_encoding``, or
            ``awaiting_publishing``.
        :type table: ``unicode``
        :param page: Page number, defaults to 1.
        :type page: int
        :rtype: dict
        :returns:
            media
                A list of :class:`~mediadrop.model.media.Media` instances.

        """
        return dict(
            media = self._fetch_page(table, page).items,
        )


    def _fetch_page(self, type='awaiting_review', page=1, items_per_page=6):
        """Helper method for paginating media results"""
        query = Media.query.order_by(Media.modified_on.desc())

        if type == 'awaiting_review':
            query = query.filter_by(reviewed=False)
        elif type == 'awaiting_encoding':
            query = query.filter_by(reviewed=True, encoded=False)
        elif type == 'awaiting_publishing':
            query = query.filter_by(reviewed=True, encoded=True, publishable=False)
        query = query.filter_by(author_name=request.perm.user.display_name)

        return webhelpers.paginate.Page(query, page, items_per_page)
