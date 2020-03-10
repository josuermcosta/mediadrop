
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

    def json_error(self, *args, **kwargs):
        validation_exception = tmpl_context._current_obj().validation_exception
        return dict(success=False, message=validation_exception.msg)


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
        if id != 'new':
            if media.author_name != user:
                media = fetch_row(Media, 'NONE')
            # Pull the defaults from the media item
        print('cheguei aqui')
        if tmpl_context.action == 'save' or id == 'new':
            # Use the values from error_handler or GET for new podcast media
            media_values = kwargs
            user = request.perm.user
            media_values.setdefault('author_name', user.display_name)
            media_values.setdefault('author_email', user.email_address)
        else:
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
        if id != 'new':
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



    @expose('json', request_method='POST')
    @validate(add_file_form, error_handler=json_error)
    @autocommit
    @observable(events.Admin.MediaController.add_file)
    def add_file(self, id, file=None, url=None, **kwargs):
        """Save action for the :class:`~mediadrop.forms.admin.media.AddFileForm`.

        Creates a new :class:`~mediadrop.model.media.MediaFile` from the
        uploaded file or the local or remote URL.

        :param id: Media ID. If ``"new"`` a new Media stub is created.
        :type id: :class:`int` or ``"new"``
        :param file: The uploaded file
        :type file: :class:`cgi.FieldStorage` or ``None``
        :param url: A URL to a recognizable audio or video file
        :type url: :class:`unicode` or ``None``
        :rtype: JSON dict
        :returns:
            success
                bool
            message
                Error message, if unsuccessful
            media_id
                The :attr:`~mediadrop.model.media.Media.id` which is
                important if new media has just been created.
            file_id
                The :attr:`~mediadrop.model.media.MediaFile.id` for the newly
                created file.
            edit_form
                The rendered XHTML :class:`~mediadrop.forms.admin.media.EditFileForm`
                for this file.
            status_form
                The rendered XHTML :class:`~mediadrop.forms.admin.media.UpdateStatusForm`

        """
        if id == 'new':
            media = Media()
            user = request.perm.user
            media.author = Author(user.display_name, user.email_address)
            # Create a temp stub until we can set it to something meaningful
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            media.title = u'Temporary stub %s' % timestamp
            media.slug = get_available_slug(Media, '_stub_' + timestamp)
            media.reviewed = True
            DBSession.add(media)
            DBSession.flush()
        else:
            media = fetch_row(Media, id)
        try:
            media_file = add_new_media_file(media, file, url)
        except UserStorageError as e:
            return dict(success=False, message=e.message)
        if media.slug.startswith('_stub_'):
            media.title = file.filename
            media.slug = get_available_slug(Media, '_stub_' + media.title)

        # The thumbs may have been created already by add_new_media_file
        print('i am here')
        if id == 'new' and not has_thumbs(media):
            create_default_thumbs_for(media)

        media.update_status()

        # Render some widgets so the XHTML can be injected into the page
        edit_form_xhtml = unicode(edit_file_form.display(
            action=url_for(action='edit_file', id=media.id),
            file= media_file))
        status_form_xhtml = unicode(update_status_form.display(
            action=url_for(action='update_status', id=media.id),
            media=media))
        data = dict(
            success = True,
            media_id = media.id,
            file_id = media_file.id,
            file_type = media_file.type,
            edit_form = edit_form_xhtml,
            status_form = status_form_xhtml,
            title = media.title,
            slug = media.slug,
            description = media.description,
            link = url_for(action='edit', id=media.id),
            duration = helpers.duration_from_seconds(media.duration),
        )

        return data

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

    @expose('json', request_method='POST')
    @autocommit
    @observable(events.Admin.MediaController.save_thumb)
    def save_thumb(self, id, thumb=None, **kwargs):
        """Save a thumbnail uploaded with :class:`~mediadrop.forms.admin.ThumbForm`.

        :param id: Media ID. If ``"new"`` a new Media stub is created.
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
                The :attr:`~mediadrop.model.media.Media.id` which is
                important if a new media has just been created.

        """
        user = request.perm.user
        if id == 'new':
            media = Media()
            user = request.perm.user
            media.author = Author(user.display_name, user.email_address)
            media.title = os.path.basename(kwargs['file'].filename)
            media.slug = get_available_slug(Media, '_stub_' + media.title)
            DBSession.add(media)
            DBSession.flush()
        else:
            media = fetch_row(Media, id)
            group = request.perm.user.groups[0].group_name
            if media.author.name != user.display_name and group != 'admins':
                raise


        try:
            # Create JPEG thumbs
            create_thumbs_for(media, kwargs['file'].file, kwargs['file'].filename)
            success = True
            message = None
        except IOError, e:
            success = False
            if id == 'new':
                DBSession.delete(media)
            if e.errno == 13:
                message = _('Permission denied, cannot write file')
            elif e.message == 'cannot identify image file':
                message = _('Unsupported image type: %s') \
                    % os.path.splitext(kwargs['file'].filename)[1].lstrip('.')
            elif e.message == 'cannot read interlaced PNG files':
                message = _('Interlaced PNGs are not supported.')
            else:
                raise
        except Exception:
            if id == 'new':
                DBSession.delete(media)
            raise


        return dict(
            success = success,
            message = message,
            id = media.id,
            title = media.title,
            slug = media.slug,
            link = url_for(action='edit', id=media.id),
        )


    @expose('json', request_method='POST')
    @validate(update_status_form, error_handler=edit)
    @autocommit
    @observable(events.Admin.MediaController.update_status)
    def update_status(self, id, status=None, publish_on=None, publish_until=None, **values):
        """Update the publish status for the given media.

        :param id: Media ID
        :type id: ``int``
        :param update_status: The text of the submit button which indicates
            that the :attr:`~mediadrop.model.media.Media.status` should change.
        :type update_status: ``unicode`` or ``None``
        :param publish_on: A date to set to
            :attr:`~mediadrop.model.media.Media.publish_on`
        :type publish_on: :class:`datetime.datetime` or ``None``
        :param publish_until: A date to set to
            :attr:`~mediadrop.model.media.Media.publish_until`
        :type publish_until: :class:`datetime.datetime` or ``None``
        :rtype: JSON dict
        :returns:
            success
                bool
            message
                Error message, if unsuccessful
            status_form
                Rendered XHTML for the status form, updated to reflect the
                changes made.

        """
        media = fetch_row(Media, id)
        new_slug = None

        # Make the requested change assuming it will be allowed
        if status == 'unreviewed':
            media.reviewed = True
        elif status == 'draft':
            self._publish_media(media, publish_on)
        elif publish_on:
            media.publish_on = publish_on
            media.update_popularity()
        elif publish_until:
            media.publish_until = publish_until

        # Verify the change is valid by re-determining the status
        media.update_status()
        DBSession.flush()

        if request.is_xhr:
            # Return the rendered widget for injection
            status_form_xhtml = unicode(update_status_form.display(
                action=url_for(action='update_status'), media=media))
            return dict(
                success = True,
                status_form = status_form_xhtml,
                slug = new_slug,
            )
        else:
            redirect(action='edit')

    @expose('json', request_method='POST')
    @autocommit
    @observable(events.Admin.MediaController.bulk)
    def bulk(self, type=None, ids=None, **kwargs):
        """Perform bulk operations on media items

        :param type: The type of bulk action to perform (delete)
        :param ids: A list of IDs.

        """
        if not ids:
            ids = []
        elif not isinstance(ids, list):
            ids = [ids]

        media = Media.query.filter(Media.id.in_(ids)).all()
        success = True
        rows = None

        def render_rows(media):
            rows = {}
            for m in media:
                stream = render('admin/media/index-table.html', {'media': [m]})
                rows[m.id] = unicode(stream.select('table/tbody/tr'))
            return rows

        if type == 'review':
            for m in media:
                m.reviewed = True
            rows = render_rows(media)
        elif type == 'publish':
            for m in media:
                m.reviewed = True
                if m.encoded:
                    self._publish_media(m)
            rows = render_rows(media)
        elif type == 'delete':
            for m in media:
                self._delete_media(m)
        else:
            success = False

        return dict(
            success = success,
            ids = ids,
            rows = rows,
        )

    def _publish_media(self, media, publish_on=None):
        media.publishable = True
        media.publish_on = publish_on or media.publish_on or datetime.now()
        media.update_popularity()
        # Remove the stub prefix if the user wants the default media title
        if media.slug.startswith('_stub_'):
            new_slug = get_available_slug(Media, media.slug[len('_stub_'):])
            media.slug = new_slug

    def _delete_media(self, media):
        # FIXME: Ensure that if the first file is deleted from the file system,
        #        then the second fails, the first file is deleted from the
        #        file system and not linking to a nonexistent file.
        # Delete every file from the storage engine
        for file in media.files:
            file.storage.delete(file.unique_id)
            # Remove this item from the DBSession so that the foreign key
            # ON DELETE CASCADE can take effect.
            DBSession.expunge(file)
        # Delete the media
        DBSession.delete(media)
        DBSession.flush()
        # Cleanup the thumbnails
        delete_thumbs(media)
