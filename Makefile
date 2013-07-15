VERSION = $(shell egrep "^VERSION" setup.py | awk '{print $$3}')
VENV_DIR = tests/.venv

sdist:
	python setup.py sdist

rpm: sdist
	rpmbuild -ba novaimagebuilder.spec --define "_sourcedir `pwd`/dist"

srpm: sdist
	rpmbuild -bs novaimagebuilder.spec --define "_sourcedir `pwd`/dist"

clean:
	rm -rf MANIFEST build dist
