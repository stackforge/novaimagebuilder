from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
import logging
import json

Base = declarative_base()
engine = create_engine('sqlite:///imagebuilder.db', echo=True)
Session = sessionmaker(bind=engine)

class Build(Base):
    __tablename__ = 'imagebuilder_builds'
 
    id = Column(String, primary_key=True)
    status = Column(String)
    name = Column(String)
    glance_id = Column(String)
    cinder_id = Column(String)
    nova_id = Column(String)
 
    def __init__(self, id, name):
        self.id = id   
        self.name = name
     
    def __repr__(self):
        return "<Build('%s','%s')>" % (self.name, self.id)

class SQLAlchemyPersistentBuildManager(object):
    """ TODO: Docstring for PersistentBuildManager  """

    def __init__(self):
        self.log = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))
        self.session = Session()

    def build_with_id(self, build_id):
        """
        TODO: Docstring for build_with_id

        @param build_id TODO 

        @return TODO
        """
        build = self.session.query(Build).filter_by(id=build_id) 
        
        return self._builds_from_iterative(build)

    def add_build(self, build):
        """
        Add a PersistentBuild-type object to this PersistenBuildManager
        This should only be called with an build that has not yet been added to the store.
        To retrieve a previously persisted build use build_with_id() or build_query()

        @param build TODO 

        @return TODO
        """

        return self._save_build(build)

    def save_build(self, build):
        """
        TODO: Docstring for save_build

        @param build TODO

        @return TODO
        """
        self._save_build(build)

    def _save_build(self, build):
        try:
            b = Build(build['id'], build['name'])
            b.status = build['state']
            self.session.add(b)
            self.session.commit()
            self.log.debug("Saved metadata for build (%s)" % (b))
            return b.id
        except Exception as e:
            self.log.debug('Exception caught: %s' % e)
            raise Exception('Unable to save build metadata: %s' % e)

    def get_all_builds(self):
        builds = self.session.query(Build).all()
        return self._builds_from_iterative(builds)
    
    def builds_from_query(self, query):
        if not query:
            return self.get_all_builds()

    def _builds_from_iterative(self, iterative):
        builds = []
        for build in iterative:
            build_dict = {}
            build_dict['id'] = build.id
            build_dict['name'] = build.name
            build_dict['status'] = build.status
            build_dict['glance_id'] = build.glance_id
            build_dict['cinder_id'] = build.cinder_id
            build_dict['nova_id'] = build.cinder_id
            builds.append(build_dict)
        return builds

Base.metadata.create_all(engine) 
