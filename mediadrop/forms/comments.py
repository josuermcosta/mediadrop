# This file is a part of MediaDrop (https://www.mediadrop.video),
# Copyright 2009-2018 MediaDrop contributors
# For the exact contribution history, see the git revision log.
# The source code contained in this file is licensed under the GPLv3 or
# (at your option) any later version.
# See LICENSE.txt in the main project directory, for more information.

from formencode import Schema

from mediadrop.forms import TextField, XHTMLValidator, email_validator
from mediadrop.lib.i18n import N_

class PostCommentSchema(Schema):
    body = XHTMLValidator(not_empty=True)
