# This file is a part of MediaDrop (https://www.mediadrop.video),
# Copyright 2009-2018 MediaDrop contributors
# For the exact contribution history, see the git revision log.
# The source code contained in this file is licensed under the GPLv3 or
# (at your option) any later version.
# See LICENSE.txt in the main project directory, for more information.
"""
Comment Moderation Controller
"""

from pylons import request
from sqlalchemy import orm, or_

from mediadrop.forms.admin import SearchForm
from mediadrop.forms.admin.comments import EditCommentForm
from mediadrop.lib.auth import has_permission
from mediadrop.lib.base import BaseController
from mediadrop.lib.decorators import (autocommit, expose, expose_xhr,
    observable, paginate)
from mediadrop.lib.helpers import redirect, url_for
from mediadrop.model import Comment, Media, fetch_row
from mediadrop.model.meta import DBSession
from mediadrop.plugin import events

import logging
log = logging.getLogger(__name__)

edit_form = EditCommentForm()
search_form = SearchForm(action=url_for(controller='/admin/comments',
                                        action='index'))

class CommentsController(BaseController):
    @expose_xhr('users/comments/index.html',
                'users/comments/index-table.html')
    @paginate('comments', items_per_page=25)
    @observable(events.Admin.CommentsController.index)
    def index(self, page=1, search=None, media_filter=None,type=None, **kwargs):
        """List comments with pagination and filtering.

        :param page: Page number, defaults to 1.
        :type page: int
        :param search: Optional search term to filter by
        :type search: unicode or None
        :param media_filter: Optional media ID to filter by
        :type media_filter: int or None
        :rtype: dict
        :returns:
            comments
                The list of :class:`~mediadrop.model.comments.Comment` instances
                for this page.
            edit_form
                The :class:`mediadrop.forms.admin.comments.EditCommentForm` instance,
                to be rendered for each instance in ``comments``.
            search
                The given search term, if any
            search_form
                The :class:`~mediadrop.forms.admin.SearchForm` instance
            media_filter
                The given podcast ID to filter by, if any
            media_filter_title
                The media title for rendering if a ``media_filter`` was specified.

        """
        comments = Comment.query.trash(False)\
            .order_by(Comment.reviewed.asc(),
                      Comment.created_on.desc())
        user = request.perm.user.display_name

        # This only works since we only have comments on one type of content.
        # It will need re-evaluation if we ever add others.
        comments = comments.options(orm.eagerload('media'))

        if search is not None:
            comments = comments.search(search)

        comments = comments.filter(or_(Comment.author_name == user,Comment.media.has(Media.author_name == user)))

        media_filter_title = media_filter
        if media_filter is not None:
            comments = comments.filter()
            media_filter_title = DBSession.query(Media.title).get(media_filter)
            media_filter = int(media_filter)

        return dict(
            comments = comments,
            edit_form = edit_form,
            media_filter = media_filter,
            media_filter_title = media_filter_title,
            search = search,
            search_form = search_form,
        )

    @expose('json', request_method='POST')
    @autocommit
    @observable(events.Admin.CommentsController.save_edit)
    def save_edit(self, id, body, **kwargs):
        """Save an edit from :class:`~mediadrop.forms.admin.comments.EditCommentForm`.

        :param id: Comment ID
        :type id: ``int``
        :rtype: JSON dict
        :returns:
            success
                bool
            body
                The edited comment body after validation/filtering

        """
        comment = fetch_row(Comment, id)
        if comment.author_name == request.perm.user.display_name:
            comment.body = body
            comment.reviewed = False
            comment.publishable = False
            DBSession.add(comment)
            return dict(
                success = True,
                body = comment.body,
            )
        else:
            return dict(
                success = False,
                body = comment.body,
            )
