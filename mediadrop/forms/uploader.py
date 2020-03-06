# This file is a part of MediaDrop (https://www.mediadrop.video),
# Copyright 2009-2018 MediaDrop contributors
# For the exact contribution history, see the git revision log.
# The source code contained in this file is licensed under the GPLv3 or
# (at your option) any later version.
# See LICENSE.txt in the main project directory, for more information.

from tw.api import WidgetsList
from tw.forms.validators import FieldStorageUploadConverter
from tw.forms import SingleSelectField, HiddenField

from mediadrop.lib.i18n import N_
from mediadrop.forms import ListForm, TextField, XHTMLTextArea, FileField, SubmitButton, email_validator
from mediadrop.plugin import events
from mediadrop.model import Category, DBSession, Podcast

validators = dict(
    description = XHTMLTextArea.validator(
        messages = {'empty': N_('At least give it a short description...')},
        not_empty = True,
    ),
    name = TextField.validator(
        messages = {'empty': N_("You've gotta have a name!")},
        not_empty = True,
    ),
    title = TextField.validator(
        messages = {'empty': N_("You've gotta have a title!")},
        not_empty = True,
    )
)

class UploadForm(ListForm):
    template = 'upload/form.html'
    id = 'upload-form'
    css_class = 'form'
    show_children_errors = False
    params = ['async_action']

    event = events.UploadForm

    class fields(WidgetsList):
        #name = TextField(validator=validators['name'], label_text=N_('Your Name:'), maxlength=50,)
        #email = TextField(validator=email_validator(not_empty=True), label_text=N_('Your Email:'), help_text=N_('(will never be published)'), maxlength=255)
        podcast_include = SingleSelectField('podcast', label_text=N_('Include in the Podcast'), css_classes=['dropdown-select'],
                                                                     options=lambda: [(None, None)] + DBSession.query(Podcast.id, Podcast.title).all())
        title = TextField(validator=validators['title'], label_text=N_('Title:'), maxlength=255)
        description = XHTMLTextArea(validator=validators['description'], label_text=N_('Description:'), attrs=dict(rows=5, cols=25))
        file = FileField(validator=FieldStorageUploadConverter(if_missing=None, messages={'empty':N_('Oops! You forgot to enter a file.')}))
        submit = SubmitButton(default=N_('Submit'), css_classes=['mcore-btn', 'btn-submit'])