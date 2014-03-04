import os
import sys
import subprocess
import shutil

# Define some constants that will be useful.
SOURCE_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPONENT = SOURCE_FOLDER[SOURCE_FOLDER.rfind(os.sep) + 1:]

# Now add buildscripts to our python path.
sys.path.append(os.path.abspath(os.path.join(SOURCE_FOLDER, '../..', 'code/buildscripts')))

import csandbox as sandbox
import ioutil

RUN_ROOT = sandbox.current.get_run_root()
BUILT_ROOT = sandbox.current.get_built_root()
TOP_COMPONENT = sandbox.current.get_top_component()
EXTENSIONS = os.path.join(RUN_ROOT, 'webapp','extensions')
CONF_D_ASSEMBLER = os.path.join(RUN_ROOT, 'bin', 'conf_d_extension.py')

# Ignored elements
IGNORED_ITEMS = ['metadata.txt', 'build.xml', '.if_top', 'install', 'Makefile', '.bzr', 'classes']
IGNORED_EXTENSIONS = ['.pyc', '~', '.cmake', '.class']

def ignore_items(item):
    name = item.strip(os.path.sep).split(os.path.sep)[-1]
    if name in IGNORED_ITEMS:
        return False
    for ext in IGNORED_EXTENSIONS:
        if name.endswith(ext):
            return False
    return True

def _call_assemble_run(component):
    try:
        built_path = os.path.join(sandbox.current.get_built_root(), component)
        code_path = os.path.join(sandbox.current.get_code_root(), component)
        assemble_script = os.path.join(built_path, '.if_top/', 'assemble_run.py')
        if not os.path.isfile(assemble_script):
            assemble_script = os.path.join(code_path, '.if_top/', 'assemble_run.py')
        if os.path.isfile(assemble_script):
            subprocess.check_call('python "%s"' % assemble_script, shell=True, cwd=os.getcwd())
        #else:
        #    print 'Warning: Pre-built component %s is invalid' % component
    except subprocess.CalledProcessError:
        print 'Warning: assemble_run.py failed for the %s pre-built component' % component

def copy_file(src, dest):
    if not os.path.isdir(os.path.dirname(dest)):
        os.makedirs(os.path.dirname(dest))
    if not os.path.exists(dest) or os.path.getmtime(src) > os.path.getmtime(dest):
        shutil.copy2(src, dest)

def main():
    built = os.path.join(BUILT_ROOT, COMPONENT, ".")
    run = os.path.join(EXTENSIONS, "CPC")
    ioutil.transform_tree(built, run, item_filter=ignore_items)

    os.system("python %s" % CONF_D_ASSEMBLER)

    return 0

if __name__ == '__main__':
    main()
