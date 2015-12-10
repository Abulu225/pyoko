# -*-  coding: utf-8 -*-
"""
"""

# Copyright (C) 2015 ZetaOps Inc.
#
# This file is licensed under the GNU General Public License v3
# (GPLv3).  See LICENSE.txt for details.
import six
from .node import Node, FakeContext
from . import fields as field
from .db.base import DBObjects
from .lib.utils import un_camel, lazy_property, pprnt
import weakref
from .modelmeta import model_registry

super_context = FakeContext()


class Model(Node):
    objects = DBObjects
    _TYPE = 'Model'

    _DEFAULT_BASE_FIELDS = {
        'timestamp': field.TimeStamp(),
        'deleted': field.Boolean(default=False, index=True)}
    _SEARCH_INDEX = ''

    def __init__(self, context=None, **kwargs):
        self._riak_object = None

        self.unpermitted_fields = []
        self.is_unpermitted_fields_set = False
        self.context = context
        self.verbose_name = kwargs.get('verbose_name')
        self.reverse_name = kwargs.get('reverse_name')
        self._pass_perm_checks = kwargs.pop('_pass_perm_checks', False)
        # if not self._pass_perm_checks:
        #     self.row_level_access(context)
        #     self.apply_cell_filters(context)
        self.objects._pass_perm_checks = self._pass_perm_checks
        # self._prepare_linked_models()
        self._is_one_to_one = kwargs.pop('one_to_one', False)
        self.title = kwargs.pop('title', self.__class__.__name__)
        self.root = self
        self.new_back_links = []
        kwargs['context'] = context
        super(Model, self).__init__(**kwargs)

        self.objects.set_model(model=self)
        self._instance_registry.add(weakref.ref(self))
        self.saved_models = []

    def prnt(self):
        try:
            pprnt(self._data)
        except:
            pprnt(self.clean_value())

    def __eq__(self, other):
        return self._data == other._data and self.key == other.key

    def __hash__(self):
        return hash(self.key)

    def is_in_db(self):
        """
        is this model stored to db
        :return:
        """
        return self.key and not self.key.startswith('TMP_')

    def get_choices_for(self, field):

        choices = self._fields[field].choices
        if isinstance(choices, six.string_types):
            return self._choices_manager.get_all(choices)
        else:
            return choices

    @classmethod
    def get_search_index(cls):
        if not cls._SEARCH_INDEX:
            # cls._SEARCH_INDEX = settings.get_index(cls._get_bucket_name())
            cls._SEARCH_INDEX = cls.objects.bucket.get_property('search_index')
        return cls._SEARCH_INDEX

    def set_data(self, data, from_db=False):
        """
        first calls supers load_data
        then fills linked models

        :param from_db: if data coming from db then we will
        use related field type's _load_data method
        :param data: data
        :return:
        """
        self._load_data(data, from_db)
        return self

    def apply_cell_filters(self, context):
        self.is_unpermitted_fields_set = True
        for perm, fields in self.Meta.field_permissions.items():
            if not context.has_permission(perm):
                self.unpermitted_fields.extend(fields)
        return self.unpermitted_fields

    def get_unpermitted_fields(self):
        return (self.unpermitted_fields if self.is_unpermitted_fields_set else
                self.apply_cell_filters(self.context))

    @staticmethod
    def row_level_access(context, objects):
        """
        Define your query filters in here to enforce row level access control
        context should contain required user attributes and permissions
        eg:
            self.objects = self.objects.filter(user=context.user.key)
        """
        # FIXME: Row level access control should be enforced on cached related objects
        #  currently it's only work on direct queries
        pass

    @lazy_property
    def _name(self):
        return un_camel(self.__class__.__name)

    @lazy_property
    def _name_id(self):
        return "%s_id" % self._name

    # def _get_back_links(self):
    #     """
    #     get models that linked from this models
    #     :return: [Model]
    #     """
    #     return model_registry.link_registry[self.__class__]

    def update_new_linked_model(self, linked_mdl_ins, name, o2o):
        for links in linked_mdl_ins._linked_models.values():
            for lnk in links:
                mdl = lnk['mdl']
                local_field_name = lnk['field']
                remote_name = lnk['reverse']
                remote_field_name = un_camel(mdl.__name__)
                if lnk['field'] == name and isinstance(self, mdl):
                    if not o2o:
                        remote_set = getattr(linked_mdl_ins, remote_field_name)
                        if self not in remote_set:
                            remote_set(**{remote_field_name: self.root})
                            linked_mdl_ins.save()
                    else:
                        setattr(linked_mdl_ins, remote_name, self.root)
                        linked_mdl_ins.save()

    def save(self):
        self.objects.save_model(self)
        for i in range(len(self.new_back_links)):
            if self.new_back_links:
                self.update_new_linked_model(*self.new_back_links.pop())
        return self

    def delete(self):
        """
        this method just flags the object as "deleted" and saves it to db
        """
        self.deleted = True
        self.save()


class LinkProxy(object):
    _TYPE = 'Link'

    def __init__(self, link_to, one_to_one=False, verbose_name=None, reverse_name=None):
        self.link_to = link_to
        self.one_to_one = one_to_one
        self.verbose_name = verbose_name
        self.reverse_name = reverse_name
