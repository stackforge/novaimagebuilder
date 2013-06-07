#
#   Copyright 2013 Red Hat, Inc.
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.


from pecan.rest import RestController
from wsmeext.pecan import wsexpose as expose
from wsme import types as wtypes
from MongoPersistentBuildManager import MongoPersistentBuildManager
from uuid import uuid4 as uuid


class Build(object):
    identifier = wtypes.text
    _id = wtypes.text

    def __init__(self, props={}):
        for k in props.keys():
            setattr(self, k, props[k])

class BuildController(RestController):
    def __init__(self):
        self.pim = MongoPersistentBuildManager()

    # RESOURCE PATH: [GET] /osib/v1/builds
    @expose([Build])
    def get_all(self):
        builds = []
        for item in self.pim.all_builds():
            builds.append(Build(item))
        return builds

    # RESOURCE PATH: [GET] /osib/v1/builds/:uuid
    @expose(Build, wtypes.text)
    def get_one(self, build_id):
        data = self.pim.build_with_id(build_id)
        return Build(data)

    # RESOURCE PATH: [POST] /osib/v1/builds
    @expose(Build)
    def post(self):
        build = {'identifier': str(uuid())}
        self.pim.add_build(build)
        return Build(build)

    # RESOURCE PATH: [PUT] /osib/v1/builds/:uuid
    @expose(Build, wtypes.text, wtypes.text)
    def put(self, build_id, build_updates):
        build = self.pim.build_with_id(build_id)
        build.update(build_updates)
        self.pim.save_build(build)
        return Build(build)

    # RESOURCE PATH: [DELETE] /osib/v1/builds/:uuid
    @expose(wtypes.text)
    def delete(self, build_id):
        self.pim.delete_build_with_id(build_id)