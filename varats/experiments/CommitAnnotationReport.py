"""
Implements the commit-flow report with an annotation-script.

This class implements the commit-flow report (CFR) analysis of the variability-
aware region analyzer (VaRA).
For annotation we use the annotation script by Florian Niederhuber, which can
be accessed via the site-packages folder due to the installation via the
Package manager pip.
"""
import os

from benchbuild.extensions import base, time, run, compiler
from benchbuild.experiment import Experiment
from benchbuild.settings import CFG
from benchbuild.utils import actions
from benchbuild.utils.actions import Step
from benchbuild.utils.cmd import extract_bc, wllvm, opt, cp
from plumbum import local
import benchbuild.utils.settings as s

# These two new config parameters are needed to include Niederhuber's prepare-
# script and to make the folder in which the results of the analyses are
# stored user-defined.
CFG["vara"] = {
    "prepare": {
        "default": "",
        "desc": "Path to the prepare script of Niederhuber in VaRA"
    },
    "outfile": {
        "default": "",
        "desc": "Path to store results of VaRA CFR analysis."
    },
    "result": {
        "default": s.ConfigPath(local.path(os.getcwd()) / "annotatedResults"),
        "desc": "Path to store already annotated projects."
    }
}


class RunWLLVM(base.Extension):
    """
    This extension implements the WLLVM compiler.

    This class is an extension that implements the WLLVM compiler with the
    required flags LLVM_COMPILER=clang and LLVM_OUTPUFILE=<path>. This compiler
    is used to transfer the complete project into LLVM-IR.
    """

    def __cal__(self, *args, **kwargs):
        with local.env(LLVM_COMPILER="clang", LLVM_OUTPUT_FILE="{}".format(
                        local.path(str(CFG["tmp_dir"])) / "wllvm.log")):
            res = self.call_next(wllvm, *args, **kwargs)
        return res


class Prepare(Step):
    NAME = "PREPARE"
    DESCRIPTION = "Prepares the analysis by annotating the project with the \
        annotation-script of Florian Niederhuber that is provided through \
        prepare.sh."


class Extract(Step):
    NAME = "EXTRACT"
    DESCRIPTION = "Extract bitcode out of the execution file."


class Analyse(Step):
    NAME = "ANALYSE"
    DESCRIPTION = "Analyses the bitcode with CFR of VaRA."


class CommitAnnotationReport(Experiment):
    """
    Generates a commit flow report (CFR) of the project(s) specified in the
    call.
    """

    NAME = "CommitAnnotationReport"

    def actions_for_project(self, project):
        """Returns the specified steps to run the project(s) specified in
        the call in a fixed order."""

        # Add the required runtime extensions to the project(s).
        project.runtime_extension = run.RuntimeExtension(project, self) \
                                    << time.RunWithTime()

        # Add the required compiler extensions to the project(s).
        project.compiler_extension = compiler.RunCompiler(project, self) \
                                     << RunWLLVM() \
                                     << run.WithTimeout()

        # This c-flag is provided by VaRA and it suggests to use the commit
        # annotation.
        project.cflags = ["-fvara-handleRM=Commit"]

        # Builds the path where the source code of the project is located.
        project_src = project.builddir / project.src_dir

        def evaluate_preparation():
            """
            This step annotates the project with the annotation script of
            Florian Niederhuber provided in the prepare-script (prepare.sh).
            prepare.sh can be accessed via the site-packages folder of all
            python packages installed via pip.
            """
            prepare = local["prepare.sh"]

            # Move the standard project source directory to the "out" folder,
            # created in the prepare script, to acces the annotated source code.
            project.src_dir = project.src_dir / "out"

            with local.cwd(project_src):
                prepare("-c", str(CFG["env"]["path"][0]), "-t",
                        str(CFG["vara"]["prepare"].value))

        def evaluate_extraction():
            """
            This step extracts the bitcode of the executable of the project
            into one file.
            """
            with local.cwd(project_src / "out"):
                extract_bc(project.name)
                cp(local.path(project_src / "out" / project.name + ".bc"),
                   local.path(
                       str(CFG["vara"]["result"].value)) / project.name + ".bc")

        def evaluate_analysis():
            """
            This step performs the actual analysis with the correct flags.
            Flags:
                -vara-CFR: to run a commit flow report
                -yaml-out-file=<path>: specify the path to store the results
            """
            project_src = local.path(CFG["vara"]["result"].value)

            # Add to the user-defined path for saving the results of the
            # analysis also the name and the unique id of the project of every
            # run.
            outfile = "-yaml-out-file={}".format(
                CFG["vara"]["outfile"].value) + "/" + str(
                project.name) + "-" + str(project.run_uuid) + ".yaml"
            run_cmd = opt[
                "-vara-CFR", outfile, project_src / project.name + ".bc"]
            run_cmd()

        analysis_actions = []
        if not os.path.exists(local.path(
                str(CFG["vara"]["result"].value)) / project.name + ".bc"):
            analysis_actions.append(Prepare(self, evaluate_preparation))
            analysis_actions.append(actions.Compile(project))
            analysis_actions.append(Extract(self, evaluate_extraction))

        analysis_actions.append(Analyse(self, evaluate_analysis))
        analysis_actions.append(actions.Clean(project))

        return analysis_actions