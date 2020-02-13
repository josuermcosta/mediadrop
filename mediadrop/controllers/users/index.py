
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
    allow_only = has_permission('edit')

    @expose('users/index.html')
    @observable(events.Users.IndexController.index)
    def index(self, **kwargs):
        return