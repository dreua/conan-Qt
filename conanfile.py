#!/usr/bin/env python
# -*- coding: utf-8 -*-

from conans import ConanFile, tools
from distutils.spawn import find_executable
import os
import shutil
import configparser
from conans.client.profile_loader import _load_profile

class QtConan(ConanFile):

    def getsubmodules():
        config = configparser.ConfigParser()
        config.read('qtmodules.conf')
        res = {}
        assert config.sections()
        for s in config.sections():
            section = str(s)
            assert section.startswith("submodule ")
            assert section.count('"') == 2
            modulename = section[section.find('"') + 1 : section.rfind('"')]
            status = str(config.get(section, "status"))
            if status != "obsolete" and status != "ignore":
                res[modulename] = {"branch":str(config.get(section, "branch")), "status":status, "path":str(config.get(section, "path"))}
                if config.has_option(section, "depends"):
                    res[modulename]["depends"] = [str(i) for i in config.get(section, "depends").split()]
                else:
                    res[modulename]["depends"] = []
        return res
    submodules = getsubmodules()

    name = "Qt"
    version = "5.11.1"
    description = "Conan.io package for Qt library."
    url = "https://github.com/Tereius/conan-Qt"
    homepage = "https://www.qt.io/"
    license = "http://doc.qt.io/qt-5/lgpl.html"
    exports = ["LICENSE.md", "qtmodules.conf"]
    exports_sources = ["CMakeLists.txt"]
    settings = "os", "arch", "compiler", "build_type", "os_build", "arch_build"

    options = dict({
        "shared": [True, False],
        "fPIC": [True, False],
        "opengl": ["no", "es2", "desktop", "dynamic"],
        "openssl": [True, False],
        "GUI": [True, False],
        "widgets": [True, False],
        "config": "ANY",
        }, **{module: [True,False] for module in submodules}
    )
    no_copy_source = True
    default_options = ("shared=True", "fPIC=True", "opengl=desktop", "openssl=False", "GUI=True", "widgets=True", "config=None") + tuple(module + "=False" for module in submodules)
    short_paths = True
    build_policy = "missing"

    def build_requirements(self):
        if self.options.GUI:
            pack_names = []
            if tools.os_info.linux_distro == "ubuntu" or tools.os_info.linux_distro == "debian": 
                pack_names = ["libxcb1-dev", "libx11-dev", "libc6-dev"]
                if self.options.opengl == "desktop":
                    pack_names.append("libgl1-mesa-dev")
            elif tools.os_info.is_linux and tools.os_info.linux_distro != "arch":
                pack_names = ["libxcb-devel", "libX11-devel", "glibc-devel"]
                if self.options.opengl == "desktop":
                    pack_names.append("mesa-libGL-devel")

            if self.settings.arch == "x86":
                pack_names = [item+":i386" for item in pack_names]

            if pack_names:
                installer = tools.SystemPackageTool()
                installer.install(" ".join(pack_names)) # Install the package
        if self.settings.os == 'Android':
            self.build_requires("android-ndk/r17b@tereius/stable")
            self.build_requires("android-sdk/26.1.1@tereius/stable")
            self.build_requires("java_installer/8.0.144@bincrafters/stable")
            if self.settings.os_build == 'Windows':
                self.build_requires("strawberryperl/5.26.0@conan/stable")
                self.build_requires("msys2_installer/latest@bincrafters/stable")

    def configure(self):
        if self.options.openssl:
            self.requires("OpenSSL/1.1.0g@conan/stable")
            self.options["OpenSSL"].no_zlib = True
        if self.options.widgets == True:
            self.options.GUI = True
        if not self.options.GUI:
            self.options.opengl = "no"
        if self.settings.os == "Android":
            self.options["android-ndk"].makeStandalone = False
            if self.options.opengl != "no":
                self.options.opengl = "es2"

        assert QtConan.version == QtConan.submodules['qtbase']['branch']
        def enablemodule(self, module):
            setattr(self.options, module, True)
            for req in QtConan.submodules[module]["depends"]:
                enablemodule(self, req)
        self.options.qtbase = True
        for module in QtConan.submodules:
            if getattr(self.options, module):
                enablemodule(self, module)

    def system_requirements(self):
        if self.options.GUI:
            pack_names = []
            if tools.os_info.linux_distro == "ubuntu" or tools.os_info.linux_distro == "debian": 
                pack_names = ["libxcb1", "libx11-6"]
            elif tools.os_info.is_linux and tools.os_info.linux_distro != "opensuse":
                pack_names = ["libxcb"]

            if self.settings.arch == "x86":
                pack_names = [item+":i386" for item in pack_names]

            if pack_names:
                installer = tools.SystemPackageTool()
                installer.install(" ".join(pack_names)) # Install the package

    def source(self):
        url = "http://download.qt.io/official_releases/qt/{0}/{1}/single/qt-everywhere-src-{1}"\
            .format(self.version[:self.version.rfind('.')], self.version)
        if tools.os_info.is_windows:
            tools.get("%s.zip" % url)
        else:
            self.run("wget -qO- %s.tar.xz | tar -xJ " % url)
        shutil.move("qt-everywhere-src-%s" % self.version, "qt5")

    def build(self):
        args = ["-opensource", "-confirm-license", "-silent", "-nomake examples", "-nomake tests",
                "-prefix %s" % self.package_folder]
        if not self.options.GUI:
            args.append("-no-gui")
        if not self.options.widgets:
            args.append("-no-widgets")
        if not self.options.shared:
            args.insert(0, "-static")
            if self.settings.os == "Windows":
                if self.settings.compiler.runtime == "MT" or self.settings.compiler.runtime == "MTd":
                    args.append("-static-runtime")
        else:
            args.insert(0, "-shared")
        if self.settings.build_type == "Debug":
            args.append("-debug")
        else:
            args.append("-release")
        for module in QtConan.submodules:
            if not getattr(self.options, module) and os.path.isdir(os.path.join(self.source_folder, 'qt5', QtConan.submodules[module]['path'])):
                args.append("-skip " + module)

        # openGL
        if self.options.opengl == "no":
            args += ["-no-opengl"]
        elif self.options.opengl == "es2":
            args += ["-opengl es2"]
        elif self.options.opengl == "desktop":
            args += ["-opengl desktop"]
        if self.settings.os == "Windows":
            if self.options.opengl == "dynamic":
                args += ["-opengl dynamic"]

        # openSSL
        if not self.options.openssl:
            args += ["-no-openssl"]
        else:
            if self.options["OpenSSL"].shared:
                args += ["-openssl-linked"]
            else:
                args += ["-openssl"]
            args += ["-I %s" % i for i in self.deps_cpp_info["OpenSSL"].include_paths]
            libs = self.deps_cpp_info["OpenSSL"].libs
            lib_paths = self.deps_cpp_info["OpenSSL"].lib_paths
            os.environ["OPENSSL_LIBS"] = " ".join(["-L"+i for i in lib_paths] + ["-l"+i for i in libs])
        
        if self.options.config:
            args.append(str(self.options.config))
            
        if self.settings.os == "Windows":
            if self.settings.compiler == "Visual Studio":
                self._build_msvc(args)
            else:
                self._build_mingw(args)
        elif self.settings.os == "Android":
            self._build_android(args)
        else:
            self._build_unix(args)
            
        with open('qtbase/bin/qt.conf', 'w') as f: 
            f.write('[Paths]\nPrefix = ..')

    def _build_msvc(self, args):
        build_command = find_executable("jom.exe")
        if build_command:
            build_args = ["-j", str(tools.cpu_count())]
        else:
            build_command = "nmake.exe"
            build_args = []
        self.output.info("Using '%s %s' to build" % (build_command, " ".join(build_args)))


        with tools.vcvars(self.settings):
            self.run("%s/qt5/configure %s" % (self.source_folder, " ".join(args)))
            self.run("%s %s" % (build_command, " ".join(build_args)))
            self.run("%s install" % build_command)

    def _build_mingw(self, args):
        # Workaround for configure using clang first if in the path
        new_path = []
        for item in os.environ['PATH'].split(';'):
            if item != 'C:\\Program Files\\LLVM\\bin':
                new_path.append(item)
        os.environ['PATH'] = ';'.join(new_path)
        # end workaround
        args += ["-xplatform win32-g++"]

        with tools.environment_append({"MAKEFLAGS":"-j %d" % tools.cpu_count()}):
            self.output.info("Using '%d' threads" % tools.cpu_count())
            self.run("%s/qt5/configure.bat %s" % (self.source_folder, " ".join(args)))
            self.run("mingw32-make")
            self.run("mingw32-make install")

    def _build_unix(self, args):
        if self.settings.os == "Linux":
            if self.options.GUI:
                args.append("-qt-xcb")
            if self.settings.arch == "x86":
                args += ["-xplatform linux-g++-32"]
            elif self.settings.arch == "armv6":
                args += ["-xplatform linux-arm-gnueabi-g++"]
            elif self.settings.arch == "armv7":
                args += ["-xplatform linux-arm-gnueabi-g++"]
        else:
            args += ["-no-framework"]
            if self.settings.arch == "x86":
                args += ["-xplatform macx-clang-32"]

        with tools.environment_append({"MAKEFLAGS":"-j %d" % tools.cpu_count()}):
            self.output.info("Using '%d' threads" % tools.cpu_count())
            self.run("%s/qt5/configure %s" % (self.source_folder, " ".join(args)))
            self.run("make")
            self.run("make install")

    def _build_android(self, args):
        # end workaround
        args += ["-platform win32-g++", "-xplatform android-g++", "--disable-rpath", "-skip qttranslations", "-skip qtserialport"]
        args += ["-android-ndk-platform android-%s" % (str(self.settings.os.api_level))]
        args += ["-android-ndk " + self.deps_env_info['android-ndk'].NDK_ROOT]
        args += ["-android-sdk " + self.deps_env_info['android-sdk'].SDK_ROOT]
        args += ["-android-ndk-host %s-%s" % (str(self.settings.os_build).lower(), str(self.settings.arch_build))]
        args += ["-android-toolchain-version " + self.deps_env_info['android-ndk'].TOOLCHAIN_VERSION]
        #args += ["-sysroot " + self.deps_env_info['android-ndk'].SYSROOT]
        args += ["-device-option CROSS_COMPILE=" + self.deps_env_info['android-ndk'].CHOST + "-"]

        if str(self.settings.arch).startswith('x86'):
            args.append('-android-arch x86')
        elif str(self.settings.arch).startswith('x86_64'):
            args.append('-android-arch x86_64')
        elif str(self.settings.arch).startswith('armv6'):
            args.append('-android-arch armeabi')
        elif str(self.settings.arch).startswith('armv7'):
            args.append("-android-arch armeabi-v7a")
        elif str(self.settings.arch).startswith('armv8'):
            args.append("-android-arch arm64-v8a")

        self.output.info("Using '%d' threads" % tools.cpu_count())
        with tools.environment_append({
            #"ANDROID_API_VERSION": "android-" + str(self.settings.os.api_level),
            #"ANDROID_SDK_ROOT": self.deps_env_info['android-sdk'].SDK_ROOT,
            #"ANDROID_TARGET_ARCH": "armeabi-v7a",
            #"ANDROID_BUILD_TOOLS_REVISION": self.deps_env_info['android-sdk'].ANDROID_BUILD_TOOLS_REVISION,
            #"ANDROID_NDK_PATH": self.deps_env_info['android-ndk'].NDK_ROOT,
            #"ANDROID_TOOLCHAIN_VERSION": self.deps_env_info['android-ndk'].TOOLCHAIN_VERSION,
            #"ANDROID_NDK_HOST": "windows-x86_64"
            }):
            self.run(tools.unix_path("%s/qt5/configure %s" % (self.source_folder, " ".join(args))), win_bash=True, msys_mingw=True)
            self.run("make", win_bash=True)
            self.run("make install", win_bash=True)

    def package(self):
        self.copy("bin/qt.conf", src="qtbase")

    def package_info(self):
        if self.settings.os == "Windows":
            self.env_info.path.append(os.path.join(self.package_folder, "bin"))
        self.env_info.CMAKE_PREFIX_PATH.append(self.package_folder)
9