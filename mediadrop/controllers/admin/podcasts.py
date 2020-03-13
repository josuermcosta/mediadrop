# This file is a part of MediaDrop (https://www.mediadrop.video),
# Copyright 2009-2018 MediaDrop contributors
# For the exact contribution history, see the git revision log.
# The source code contained in this file is licensed under the GPLv3 or
# (at your option) any later version.
# See LICENSE.txt in the main project directory, for more information.

import os

from pylons import request, tmpl_context
from sqlalchemy import orm

from mediadrop.forms.admin import ThumbForm
from mediadrop.forms.admin.podcasts import PodcastForm
from mediadrop.lib.auth import has_permission
from mediadrop.lib.base import BaseController
from mediadrop.lib.decorators import (autocommit, expose, expose_xhr,
    observable, paginate, validate)
from mediadrop.lib.helpers import redirect, url_for
from mediadrop.lib.i18n import _
from mediadrop.lib.thumbnails import (create_default_thumbs_for,
    create_thumbs_for, delete_thumbs)
from mediadrop.model import Author, Podcast, fetch_row, get_available_slug
from mediadrop.model.meta import DBSession
from mediadrop.plugin import events

import logging
log = logging.getLogger(__name__)

podcast_form = PodcastForm()
thumb_form = ThumbForm()

class PodcastsController(BaseController):
    allow_only = has_permission('edit')

    @expose_xhr('admin/podcasts/index.html',
                'admin/podcasts/index-table.html')
    @paginate('podcasts', items_per_page=10)
    @observable(events.Admin.PodcastsController.index)
    def index(self, page=1, **kw):
        """List podcasts with pagination.

        :param page: Page number, defaults to 1.
        :type page: int
        :rtype: Dict
        :returns:
            podcasts
                The list of :class:`~mediadrop.model.podcasts.Podcast`
                instances for this page.
        """
        user = request.perm.user.display_name
        group = request.perm.user.groups[0].group_name
        podcasts = DBSession.query(Podcast)\
            .options(orm.undefer('media_count'))\
            .order_by(Podcast.title)
        if group != 'admins':
            podcasts = podcasts.filter(Podcast.author_name == user)
        return dict(podcasts=podcasts)


    @expose('admin/podcasts/edit.html')
    @observable(events.Admin.PodcastsController.edit)
    def edit(self, id, **kwargs):
        """Display the podcast forms for editing or adding.

        This page serves as the error_handler for every kind of edit action,
        if anything goes wrong with them they'll be redirected here.

        :param id: Podcast ID
        :type id: ``int`` or ``"new"``
        :param \*\*kwargs: Extra args populate the form for ``"new"`` podcasts
        :returns:
            podcast
                :class:`~mediadrop.model.podcasts.Podcast` instance
            form
                :class:`~mediadrop.forms.admin.podcasts.PodcastForm` instance
            form_action
                ``str`` form submit url
            form_values
                ``dict`` form values
            thumb_form
                :class:`~mediadrop.forms.admin.ThumbForm` instance
            thumb_action
                ``str`` form submit url

        """
        user = request.perm.user.display_name
        group = request.perm.user.groups[0].group_name
        podcast = fetch_row(Podcast, id)

        if id != 'new' and (user != podcast.author.name and group != 'admins'):
            return dict()

        if tmpl_context.action == 'save' or id == 'new':
            form_values = kwargs
            user = request.perm.user
            form_values.setdefault('feed', {}).setdefault('feed_url',
                _('Save the podcast to get your feed URL'))
        else:
            explicit_values = {True: 'yes', False: 'clean', None: 'no'}
            form_values = dict(
                slug = podcast.slug,
                title = podcast.title,
                subtitle = podcast.subtitle,
                description = podcast.description,
                details = dict(
                    explicit = explicit_values.get(podcast.explicit),
                    category = podcast.category,
                    copyright = podcast.copyright,
                ),
                feed = dict(
                    feed_url = url_for(controller='/podcasts', action='feed',
                                       slug=podcast.slug, qualified=True),
                    itunes_url = podcast.itunes_url,
                    feedburner_url = podcast.feedburner_url,
                ),
            )

        return dict(
            podcast = podcast,
            form = podcast_form,
            form_action = url_for(action='save'),
            form_values = form_values,
            thumb_form = thumb_form,
            thumb_action = url_for(action='save_thumb'),
        )


    @expose(request_method='POST')
    @validate(podcast_form, error_handler=edit)
    @autocommit
    @observable(events.Admin.PodcastsController.save)
    def save(self, id, slug, title, subtitle,
             description, details, feed, delete=None, **kwargs):
        """
        Save changes or create a new :class:`~mediadrop.model.podcasts.Podcast` instance.

        Form handler the :meth:`edit` action and the
        :class:`~mediadrop.forms.admin.podcasts.PodcastForm`.

        Redirects back to :meth:`edit` after successful editing
        and :meth:`index` after successful deletion.

        """
        user = request.perm.user.display_name
        group = request.perm.user.groups[0].group_name
        podcast = fetch_row(Podcast, id)

        if id != 'new' and author in podcast:
            if group != 'admins' and  podcast.author.name != user:
                redirect(action='index')

        if delete:
            DBSession.delete(podcast)
            DBSession.commit()
            delete_thumbs(podcast)
            redirect(action='index', id=None)

        user = request.perm.user.display_name
        group = request.perm.user.groups[0].group_name
        user_email = request.perm.user.email_address


        if not slug:
            slug = title
        if slug != podcast.slug:
            podcast.slug = get_available_slug(Podcast, slug, podcast)

        podcast.title = title
        podcast.subtitle = subtitle
        podcast.description = description
        podcast.copyright = details['copyright']
        podcast.category = details['category']
        podcast.itunes_url = feed['itunes_url']
        podcast.feedburner_url = feed['feedburner_url']
        podcast.explicit = {'yes': True, 'clean': False}.get(details['explicit'], None)

        if id == 'new':
            podcast.author = Author(user, user_email)
            DBSession.add(podcast)
            DBSession.flush()
            create_default_thumbs_for(podcast)
        else:
            podcast.author = Author(podcast.author.name, podcast.author.email)

        redirect(action='edit', id=podcast.id)


    @expose('json', request_method='POST')
    @validate(thumb_form, error_handler=edit)
    @observable(events.Admin.PodcastsController.save_thumb)
    def save_thumb(self, id, thumb, **values):
        """Save a thumbnail uploaded with :class:`~mediadrop.forms.admin.ThumbForm`.

        :param id: Media ID. If ``"new"`` a new Podcast stub is created.
        :type id: ``int`` or ``"new"``
        :param file: The uploaded file
        :type file: :class:`cgi.FieldStorage` or ``None``
        :rtype: JSON dict
        :returns:
            success
                bool
            message
                Error message, if unsuccessful
            id
                The :attr:`~mediadrop.model.podcasts.Podcast.id` which is
                important if a new podcast has just been created.

        """
        if id == 'new':
            return dict(
                success = False,
                message = u'You must first save the podcast before you can upload a thumbnail',
            )

        podcast = fetch_row(Podcast, id)

        try:
            # Create JPEG thumbs
            create_thumbs_for(podcast, thumb.file, thumb.filename)
            success = True
            message = None
        except IOError, e:
            success = False
            if e.errno == 13:
                message = _('Permission denied, cannot write file')
            elif e.message == 'cannot identify image file':
                message = _('Unsupport image type: %s') \
                    % os.path.splitext(thumb.filename)[1].lstrip('.')
            elif e.message == 'cannot read interlaced PNG files':
                message = _('Interlaced PNGs are not supported.')
            else:
                raise

        return dict(
            success = success,
            message = message,
        )
