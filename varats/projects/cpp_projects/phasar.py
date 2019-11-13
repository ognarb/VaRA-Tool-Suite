"""
Project file for PhASAR static analysis framework.
"""
from benchbuild.settings import CFG
from benchbuild.utils.compiler import cxx
from benchbuild.utils.run import run
from benchbuild.project import Project
from benchbuild.utils.cmd import make, cmake, cp, git
from benchbuild.utils.download import with_git

from plumbum import local

from varats.paper.paper_config import project_filter_generator


@with_git(
    "https://github.com/secure-software-engineering/phasar.git",
    limit=200,
    refspec="HEAD",
    shallow_clone=False,
    version_filter=project_filter_generator("phasar"))
class Phasar(Project):  # type: ignore
    """ PhASAR """

    NAME = 'phasar'
    GROUP = 'cpp_projects'
    DOMAIN = 'analysis-framework'
    VERSION = 'HEAD'

    BIN_NAMES = ['phasar']
    SRC_FILE = NAME + "-{0}".format(VERSION)

    def run_tests(self, runner: run) -> None:
        pass

    def compile(self) -> None:
        self.download()

        # path.local.LocalPath.mkdir(local.path("build/dev"))
        clangxx = cxx(self)
        with local.cwd(self.SRC_FILE):
            git("submodule", "init")
            git("submodule", "update")
            with local.env(CXX=str(clangxx)):
                cmake("-G", "Unix Makefiles", ".")
            run(make["-j", int(CFG["jobs"])])
