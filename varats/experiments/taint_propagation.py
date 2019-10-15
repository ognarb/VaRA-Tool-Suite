"""
Execute showcase cpp examples with VaRA to compare the taint analysis to other
statically analysis frameworks.

This class implements the full commit taint flow analysis (MTFA) graph
generation of the variability-aware region analyzer (VaRA).
We run the analyses on exemplary cpp files. Then we compare the results of the
analysis to the expected results via LLVM FileCheck.
Both the cpp examples and the filecheck files validating the results can be
found in the https://github.com/se-passau/vara-perf-tests repository.
The results of each filecheck get written into a special TaintPropagation-
Report, which lists, what examples produced the correct result and which ones
failed.
"""

import typing as tp
from os import path

from plumbum import local, ProcessExecutionError

from benchbuild.extensions import compiler, run, time
from benchbuild.settings import CFG
from benchbuild.project import Project
import benchbuild.utils.actions as actions
from benchbuild.utils.cmd import opt, mkdir, timeout, FileCheck, rm
from varats.data.reports.taint_report import TaintPropagationReport as TPR
from varats.data.report import FileStatusExtension as FSE
from varats.experiments.extract import Extract
from varats.experiments.wllvm import RunWLLVM
from varats.utils.experiment_util import (
    exec_func_with_pe_error_handler, FunctionPEErrorWrapper,
    VaRAVersionExperiment, PEErrorHandler)


class VaraMTFACheck(actions.Step):  # type: ignore
    """
    Analyse a project with VaRA and generate the output of the taint analysis.
    """

    NAME = "VaraMTFACheck"
    DESCRIPTION = "Generate a full MTFA on the exemplary taint test files and"\
        + " compare them against the expected result."

    RESULT_FOLDER_TEMPLATE = "{result_dir}/{project_dir}"

    FC_FILE_SOURCE_DIR = "{project_builddir}/{project_src}/{project_name}"
    EXPECTED_FC_FILE = "{binary_name}.txt"

    def __init__(self, project: Project):
        super(VaraMTFACheck, self).__init__(
            obj=project, action_fn=self.analyze)

    def analyze(self) -> actions.StepResult:
        """
        This step performs the actual analysis with the correct flags.
        Flags:
            -vara-CD:         activate VaRA's commit detection
            -print-Full-MTFA: to run a taint flow analysis
        """

        if not self.obj:
            return
        project = self.obj

        # Set up cache directory for bitcode files
        bc_cache_dir = Extract.BC_CACHE_FOLDER_TEMPLATE.format(
            cache_dir=str(CFG["vara"]["result"]),
            project_name=str(project.name))

        # Define the output directory.
        vara_result_folder = self.RESULT_FOLDER_TEMPLATE.format(
            result_dir=str(CFG["vara"]["outfile"]),
            project_dir=str(project.name))
        mkdir("-p", vara_result_folder)

        timeout_duration = '8h'

        for binary_name in project.BIN_NAMES:
            # Combine the input bitcode file's name
            bc_target_file = Extract.BC_FILE_TEMPLATE.format(
                project_name=str(project.name),
                binary_name=str(binary_name),
                project_version=str(project.version))

            # Define empty success file.
            result_file = TPR.get_file_name(
                project_name=str(project.name),
                binary_name=binary_name,
                project_version=str(project.version),
                project_uuid=str(project.run_uuid),
                extension_type=FSE.Success)

            # Define output file name of failed runs
            error_file = TPR.get_file_name(
                project_name=str(project.name),
                binary_name=binary_name,
                project_version=str(project.version),
                project_uuid=str(project.run_uuid),
                extension_type=FSE.Failed,
                file_ext=TPR.FILE_TYPE)

            # The temporary directory the project is stored under
            tmp_repo_dir = self.FC_FILE_SOURCE_DIR.format(
                project_builddir=str(project.builddir),
                project_src=str(project.SRC_FILE),
                project_name=str(project.name))

            # The file name of the text file with the expected filecheck regex
            expected_file = self.EXPECTED_FC_FILE.format(
                binary_name=binary_name)

            # Put together the path to the bc file and the opt command of vara
            vara_run_cmd = opt["-vara-CD", "-print-Full-MTFA",
                               "{cache_folder}/{bc_file}"
                               .format(cache_folder=bc_cache_dir,
                                       bc_file=bc_target_file),
                               "-o", "/dev/null"]

            file_check_cmd = FileCheck["{fc_dir}{fc_exp_file}".format(
                fc_dir=tmp_repo_dir, fc_exp_file=expected_file)]

            cmd_chain = timeout[timeout_duration, vara_run_cmd] \
                | file_check_cmd > "{res_folder}/{res_file}".format(
                    res_folder=vara_result_folder,
                    res_file=result_file)

            # Run the MTFA command with custom error handler and timeout
            try:
                exec_func_with_pe_error_handler(
                    cmd_chain,
                    PEErrorHandler(vara_result_folder, error_file,
                                   cmd_chain, timeout_duration))
            # Remove the success file on error in the filecheck.
            except ProcessExecutionError:
                rm("{res_folder}/{res_file}".format(
                    res_folder=vara_result_folder,
                    res_file=result_file))


class VaRATaintPropagation(VaRAVersionExperiment):
    """
    Generates a taint flow analysis (MTFA) of the project(s) specified in the
    call.
    """

    NAME = "VaRATaintPropagation"

    REPORT_TYPE = TPR

    def actions_for_project(self, project: Project) -> tp.List[actions.Step]:
        """
        Returns the specified steps to run the project(s) specified in
        the call in a fixed order.
        """

        # Add the required runtime extensions to the project(s).
        project.runtime_extension = run.RuntimeExtension(project, self) \
            << time.RunWithTime()

        # Add the required compiler extensions to the project(s).
        project.compiler_extension = compiler.RunCompiler(project, self) \
            << RunWLLVM() \
            << run.WithTimeout()

        # Add own error handler to compile step.
        project.compile = FunctionPEErrorWrapper(
            project.compile,
            PEErrorHandler(
                VaraMTFACheck.RESULT_FOLDER_TEMPLATE.format(
                    result_dir=str(CFG["vara"]["outfile"]),
                    project_dir=str(project.name)),
                TPR.get_file_name(
                    project_name=str(project.name),
                    binary_name="all",
                    project_version=str(project.version),
                    project_uuid=str(project.run_uuid),
                    extension_type=FSE.CompileError)))

        project.cflags = ["-fvara-handleRM=Commit"]

        analysis_actions = []

        # Not run all steps if cached results exist.
        all_cache_files_present = True
        for binary_name in project.BIN_NAMES:
            all_cache_files_present &= path.exists(
                local.path(
                    Extract.BC_CACHE_FOLDER_TEMPLATE.format(
                        cache_dir=str(CFG["vara"]["result"]),
                        project_name=str(project.name)) +
                    Extract.BC_FILE_TEMPLATE.format(
                        project_name=str(project.name),
                        binary_name=binary_name,
                        project_version=str(project.version))))

            if not all_cache_files_present:
                analysis_actions.append(actions.Compile(project))
                analysis_actions.append(Extract(project))
                break

        analysis_actions.append(VaraMTFACheck(project))
        analysis_actions.append(actions.Clean(project))

        return analysis_actions
