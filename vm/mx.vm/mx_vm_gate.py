# ----------------------------------------------------------------------------------------------------
#
# Copyright (c) 2018, 2018, Oracle and/or its affiliates. All rights reserved.
# DO NOT ALTER OR REMOVE COPYRIGHT NOTICES OR THIS FILE HEADER.
#
# This code is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 2 only, as
# published by the Free Software Foundation.  Oracle designates this
# particular file as subject to the "Classpath" exception as provided
# by Oracle in the LICENSE file that accompanied this code.
#
# This code is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License
# version 2 for more details (a copy is included in the LICENSE file that
# accompanied this code).
#
# You should have received a copy of the GNU General Public License version
# 2 along with this work; if not, write to the Free Software Foundation,
# Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301 USA.
#
# Please contact Oracle, 500 Oracle Parkway, Redwood Shores, CA 94065 USA
# or visit www.oracle.com if you need additional information or have any
# questions.
#
# ----------------------------------------------------------------------------------------------------

import mx
import mx_vm
import mx_subst
import mx_unittest

import functools
from mx_gate import Task

from os.path import join, exists, dirname
from contextlib import contextmanager

_suite = mx.suite('vm')


class VmGateTasks:
    compiler = 'compiler'
    substratevm = 'substratevm'
    sulong = 'sulong'
    graal_js = 'graal-js'
    graal_nodejs = 'graal-nodejs'
    truffleruby = 'truffleruby'
    ruby = 'ruby'
    python = 'python'
    fastr = 'fastr'
    graalpython = 'graalpython'
    integration = 'integration'
    tools = 'tools'
    libgraal = 'libgraal'


def gate_body(args, tasks):
    with Task('Vm: Basic GraalVM Tests', tasks, tags=[VmGateTasks.compiler]) as t:
        if t and mx_vm.has_component('Graal compiler'):
            # 1. a full open-source build should be built with an open-source JDK but we allow Oracle JDK in non-strict mode as it is common on developer machines
            # 2. the build must be a GraalVM
            # 3. the build must be JVMCI-enabled since the 'Graal compiler' component is registered
            version_regex = mx_vm.openjdk_version_regex if args.strict_mode else mx_vm.anyjdk_version_regex
            mx_vm.check_versions(mx_vm.graalvm_output(), version_regex, graalvm_version_regex=mx_vm.graalvm_version_regex, expect_graalvm=True, check_jvmci=True)

    with Task('Vm: Sulong tests', tasks, tags=[VmGateTasks.sulong]) as t:
        if t and mx_vm.has_component('Sulong', fatalIfMissing=True):
            pass

    with Task('Vm: Graal.js tests', tasks, tags=[VmGateTasks.graal_js]) as t:
        if t and mx_vm.has_component('Graal.js', fatalIfMissing=True):
            pass

    with Task('Vm: Graal.nodejs tests', tasks, tags=[VmGateTasks.graal_nodejs]) as t:
        if t and mx_vm.has_component('Graal.nodejs', fatalIfMissing=True):
            pass

    with Task('Vm: TruffleRuby tests', tasks, tags=[VmGateTasks.truffleruby]) as t:
        if t and mx_vm.has_component('TruffleRuby', fatalIfMissing=True):
            pass

    with Task('Vm: FastR tests', tasks, tags=[VmGateTasks.fastr]) as t:
        if t and mx_vm.has_component('FastR', fatalIfMissing=True):
            pass

    with Task('Vm: Graal.Python tests', tasks, tags=[VmGateTasks.graalpython]) as t:
        if t and mx_vm.has_component('Graal.Python', fatalIfMissing=True):
            pass

    if mx_vm.has_component('LibGraal'):
        libgraal_location = mx_vm.get_native_image_locations('LibGraal', 'jvmcicompiler')
        if libgraal_location is None:
            mx.warn("Skipping libgraal tests: no library enabled in the LibGraal component")
        else:
            extra_vm_argument = ['-XX:+UseJVMCICompiler', '-XX:+UseJVMCINativeLibrary', '-XX:JVMCILibPath=' + dirname(libgraal_location)]
            if args.extra_vm_argument:
                extra_vm_argument += args.extra_vm_argument
            import mx_compiler
            mx_compiler.compiler_gate_benchmark_runner(tasks, extra_vm_argument, prefix='LibGraal: ')

            with Task('Test LibGraal', tasks, tags=[VmGateTasks.libgraal]) as t:
                if t:
                    mx_unittest.unittest(["--suite", "truffle", "--"] + extra_vm_argument + ["-Dgraal.TruffleCompileImmediately=true", "-Dgraal.TruffleBackgroundCompilation=false"])

            with Task('LibGraal GraalVM smoke test', tasks, tags=[VmGateTasks.libgraal]) as t:
                if t:
                    mx.run([join(mx_vm.graalvm_home(), 'bin', 'java'), '-XX:+UseJVMCICompiler', '-XX:+UseJVMCINativeLibrary', '-jar', mx.library('DACAPO').get_path(True), 'avrora'])
    else:
        mx.warn("Skipping libgraal tests: component not enabled")

    gate_substratevm(tasks)
    gate_sulong(tasks)
    gate_ruby(tasks)
    gate_python(tasks)

def graalvm_svm():
    """
    Gives access to image building withing the GraalVM release. Requires dynamic import of substratevm.
    """
    native_image_cmd = join(mx_vm.graalvm_output(), 'bin', 'native-image')
    svm = mx.suite('substratevm')
    if not exists(native_image_cmd) or not svm:
        mx.abort("Image building not accessible in GraalVM {}. Build GraalVM with native-image support".format(mx_vm.graalvm_dist_name()))
    @contextmanager
    def native_image_context(common_args=None, hosted_assertions=True):
        with svm.extensions.native_image_context(common_args, hosted_assertions, native_image_cmd=native_image_cmd) as native_image:
            yield native_image
    return native_image_context, svm.extensions

def gate_substratevm(tasks):
    with Task('Run Truffle host interop tests on SVM', tasks, tags=[VmGateTasks.substratevm]) as t:
        if t:
            tests = ['ValueHostInteropTest', 'ValueHostConversionTest']
            truffle_no_compilation = ['--tool:truffle', '-Dtruffle.TruffleRuntime=com.oracle.truffle.api.impl.DefaultTruffleRuntime']
            truffle_dir = mx.suite('truffle').dir
            args = ['--build-args'] + truffle_no_compilation + [
                '-H:Features=com.oracle.truffle.api.test.polyglot.RegisterTestClassesForReflectionFeature',
                '-H:ReflectionConfigurationFiles=' + truffle_dir + '/src/com.oracle.truffle.api.test/src/com/oracle/truffle/api/test/polyglot/reflection.json',
                '-H:DynamicProxyConfigurationFiles=' + truffle_dir + '/src/com.oracle.truffle.api.test/src/com/oracle/truffle/api/test/polyglot/proxys.json',
                '--'
            ] + tests

            native_image_context, svm = graalvm_svm()
            with native_image_context(svm.IMAGE_ASSERTION_FLAGS) as native_image:
                svm._native_unittest(native_image, args)

def gate_sulong(tasks):
    with Task('Run SulongSuite tests as native-image', tasks, tags=[VmGateTasks.sulong]) as t:
        if t:
            lli = join(mx_vm.graalvm_output(), 'bin', 'lli')
            sulong = mx.suite('sulong')
            sulong.extensions.testLLVMImage(lli, libPath=False, unittestArgs=['--enable-timing'])

    with Task('Run Sulong interop tests as native-image', tasks, tags=[VmGateTasks.sulong]) as t:
        if t:
            sulong = mx.suite('sulong')
            native_image_context, svm = graalvm_svm()
            with native_image_context(svm.IMAGE_ASSERTION_FLAGS) as native_image:
                # TODO Use mx_vm.get_final_graalvm_distribution().find_single_source_location to rewire SULONG_LIBS
                sulong_libs = join(mx_vm.graalvm_output(), 'jre', 'languages', 'llvm')
                def distribution_paths(dname):
                    path_substitutions = {
                        'SULONG_LIBS': sulong_libs
                    }
                    return path_substitutions.get(dname, mx._get_dependency_path(dname))
                mx_subst.path_substitutions.register_with_arg('path', distribution_paths)
                sulong.extensions.runLLVMUnittests(functools.partial(svm._native_unittest, native_image))

def gate_ruby(tasks):
    with Task('Ruby', tasks, tags=[VmGateTasks.ruby]) as t:
        if t:
            # Debug GR-9912 on Ruby gate runs. If debug_gr_9912 goes away the custom image building below is not required anymore and
            # test_ruby can be called with the original graalvm ruby-launcher
            debug_gr_9912 = 16
            native_image_context, svm = graalvm_svm()
            with native_image_context(svm.IMAGE_ASSERTION_FLAGS) as native_image:
                ruby_bindir = join(mx_vm.graalvm_output(), 'jre', 'languages', 'ruby', 'bin')
                ruby_image = native_image(['--language:ruby', '-H:Path=' + ruby_bindir, '-H:GreyToBlackObjectVisitorDiagnosticHistory=' + str(debug_gr_9912)])
                truffleruby_suite = mx.suite('truffleruby')
                truffleruby_suite.extensions.ruby_testdownstream_aot([ruby_image, 'spec', 'release'])

def gate_python(tasks):
    with Task('Python', tasks, tags=[VmGateTasks.python]) as t:
        if t:
            python_svm_image_path = join(mx_vm.graalvm_output(), 'bin', 'graalpython')
            python_suite = mx.suite("graalpython")
            python_suite.extensions.run_python_unittests(python_svm_image_path)
