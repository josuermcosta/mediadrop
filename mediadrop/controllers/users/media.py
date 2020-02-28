
import os
from datetime import datetime

from formencode import Invalid, validators
from pylons import request, tmpl_context
from sqlalchemy import orm

from mediadrop.forms.admin import SearchForm, ThumbForm
from mediadrop.forms.admin.media import AddFileForm, EditFileForm, MediaForm, UpdateStatusForm
from mediadrop.lib import helpers
from mediadrop.lib.auth import has_permission
from mediadrop.lib.base import BaseController
from mediadrop.lib.decorators import (autocommit, expose, expose_xhr,
    observable, paginate, validate, validate_xhr)
from mediadrop.lib.helpers import redirect, url_for
from mediadrop.lib.i18n import _
from mediadrop.lib.storage import add_new_media_file, UserStorageError
from mediadrop.lib.templating import render
from mediadrop.lib.thumbnails import thumb_path, thumb_paths, create_thumbs_for, create_default_thumbs_for, has_thumbs, has_default_thumbs, delete_thumbs
from mediadrop.model import (Author, Category, Media, Podcast, Tag, fetch_row,
    get_available_slug, slugify)
from mediadrop.model.meta import DBSession
from mediadrop.plugin import events

import logging
log = logging.getLogger(__name__)

media_form = MediaForm()
add_file_form = AddFileForm()
edit_file_form = EditFileForm()
thumb_form = ThumbForm()
update_status_form = UpdateStatusForm()
search_form = SearchForm(action=url_for(controller='/admin/media', action='index'))

class MediaController(BaseController):
    @expose_xhr('users/media/index.html', 'users/media/index-table.html')
    @paginate('media', items_per_page=15)
    @observable(events.Admin.MediaController.index)
    def index(self, page=1, search=None, filter=None, podcast=None,
              category=None, tag=None, **kwargs):
        """List media with pagination and filtering.

        :param page: Page number, defaults to 1.
        :type page: int
        :param search: Optional search term to filter by
        :type search: unicode or None
        :param podcast_filter: Optional podcast to filter by
        :type podcast_filter: int or None
        :rtype: dict
        :returns:
            media
                The list of :class:`~mediadrop.model.media.Media` instances
                for this page.
            search
                The given search term, if any
            search_form
                The :class:`~mediadrop.forms.admin.SearchForm` instance
            podcast
                The podcast object for rendering if filtering by podcast.

        """
        user = request.perm.user.display_name

        media = Media.query.options(orm.undefer('comment_count_published'))
        media = media.filter(Media.author_name == user)

        if search:
            media = media.admin_search(search)
        else:
            media = media.order_by_status()\
                         .order_by(Media.publish_on.desc(),
                                   Media.modified_on.desc())

        if not filter:
            pass
        elif filter == 'unreviewed':
            media = media.reviewed(False)
        elif filter == 'unencoded':
            media = media.reviewed().encoded(False)
        elif filter == 'drafts':
            media = media.drafts()
        elif filter == 'published':
            media = media.published()
        if category:
            category = fetch_row(Category, slug=category)
            media = media.filter(Media.categories.contains(category))
        if tag:
            tag = fetch_row(Tag, slug=tag)
            media = media.filter(Media.tags.contains(tag))
        if podcast:
            podcast = fetch_row(Podcast, slug=podcast)
            media = media.filter(Media.podcast == podcast)

        return dict(
            media = media,
            search = search,
            search_form = search_form,
            media_filter = filter,
            category = category,
            tag = tag,
            podcast = podcast,
        )

    @expose('users/media/edit.html')
    @validate(validators={'podcast': validators.Int()})
    @autocommit
    @observable(events.Admin.MediaController.edit)
    def edit(self, id, **kwargs):
        """Display the media forms for editing or adding.

        This page serves as the error_handler for every kind of edit action,
        if anything goes wrong with them they'll be redirected here.

        :param id: Media ID
        :type id: ``int`` or ``"new"``
        :param \*\*kwargs: Extra args populate the form for ``"new"`` media
        :returns:
            media
                :class:`~mediadrop.model.media.Media` instance
            media_form
                The :class:`~mediadrop.forms.admin.media.MediaForm` instance
            media_action
                ``str`` form submit url
            media_values
                ``dict`` form values
            file_add_form
                The :class:`~mediadrop.forms.admin.media.AddFileForm` instance
            file_add_action
                ``str`` form submit url
            file_edit_form
                The :class:`~mediadrop.forms.admin.media.EditFileForm` instance
            file_edit_action
                ``str`` form submit url
            thumb_form
                The :class:`~mediadrop.forms.admin.ThumbForm` instance
            thumb_action
                ``str`` form submit url
            update_status_form
                The :class:`~mediadrop.forms.admin.media.UpdateStatusForm` instance
            update_status_action
                ``str`` form submit url

        """
        user = request.perm.user.display_name

        media = fetch_row(Media, id)
        if media.author_name != user:
            media = fetch_row(Media, 'NONE')
        # Pull the defaults from the media item
        media_values = dict(
            podcast = media.podcast_id,
            slug = media.slug,
            title = media.title,
            author_name = media.author.name,
            author_email = media.author.email,
            description = media.description,
            tags = ', '.join((tag.name for tag in media.tags)),
            categories = [category.id for category in media.categories],
            notes = media.notes,
        )

        # Re-verify the state of our Media object in case the data is nonsensical
        media.update_status()

        return dict(
            media = media,
            media_form = media_form,
            media_action = url_for(action='save'),
            media_values = media_values,
            category_tree = Category.query.order_by(Category.name).populated_tree(),
            file_add_form = add_file_form,
            file_add_action = url_for(action='add_file'),
            file_edit_form = edit_file_form,
            file_edit_action = url_for(action='edit_file'),
            thumb_form = thumb_form,
            thumb_action = url_for(action='save_thumb'),
            update_status_form = update_status_form,
            update_status_action = url_for(action='update_status'),
        )

    @expose_xhr(request_method='POST')
    @validate_xhr(media_form, error_handler=edit)
    @autocommit
    @observable(events.Admin.MediaController.save)
    def save(self, id, slug, title,
             description, notes, podcast, tags, categories,
             delete=None, **kwargs):
        """Save changes or create a new :class:`~mediadrop.model.media.Media` instance.

        Form handler the :meth:`edit` action and the
        :class:`~mediadrop.forms.admin.media.MediaForm`.

        Redirects back to :meth:`edit` after successful editing
        and :meth:`index` after successful deletion.

        """
        media = fetch_row(Media, id)
        author_name = media.author_name
        author_email = media.author_email

        if delete:
            self._delete_media(media)
            redirect(action='index', id=None)

        if not slug:
            slug = slugify(title)
        elif slug.startswith('_stub_'):
            slug = slug[len('_stub_'):]
        if slug != media.slug:
            media.slug = get_available_slug(Media, slug, media)
        media.title = title
        media.author = Author(author_name, author_email)
        media.description = description
        media.notes = notes
        media.podcast_id = podcast
        media.set_tags(tags)
        media.set_categories(categories)

        media.update_status()
        DBSession.add(media)
        DBSession.flush()

        if request.is_xhr:
            status_form_xhtml = unicode(update_status_form.display(
                action=url_for(action='update_status', id=media.id),
                media=media))

            return dict(
                media_id = media.id,
                values = {'slug': slug},
                link = url_for(action='edit', id=media.id),
                status_form = status_form_xhtml,
            )
        else:
            redirect(action='edit', id=media.id)