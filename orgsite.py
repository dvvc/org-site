#!/usr/bin/python26

"""
Generate a blog, from a set of templates and org files. Usage:

  generate.py [options]

  Options:

   - i input :: The directory where the input files are located
   - o output :: The directory where the page will be generated
   - l offset :: The headline offset (e.g. * -> H(1 + offset)
"""

import getopt
import sys
import os
import os.path
import shutil
import time

from jinja2 import Environment, FileSystemLoader
from jinja2.exceptions import TemplateNotFound

from orgpython.parser import parser
from orgpython.export.html import org_to_html

ORG_DIR = 'org'
TEMPLATES_DIR = 'templates'
MEDIA_DIR = 'media'

DEFAULT_TEMPLATE = 'default.html'

def usage():

    print __doc__
    sys.exit(1)

class Page:
    """A page is an org-mode text file"""
    def __init__(self, title, fname, author, date, html):
        self.title = title
        self.fname = fname
        self.author = author
        self.date = date
        self.html = html

class Index:
    """An index is a virtual page that has information about other pages"""
    def __init__(self, folder, pages):
        self.folder = folder
        self.pages = pages


def _filter(l, f):
    """Filters a list using function f, returns two lists, the first with the
    items for with f returns true, the second with those that produce false.
    """
    ftrue = []
    ffalse = []
    for el in l:
        if f(el):
            ftrue.append(el)
        else:
            ffalse.append(el)
    return (ftrue, ffalse)

def _find_template(templates, folder, page):
    """Finds an appropriate template for a type of page"""
 
    if folder != '':
        subdirs = folder.split('/')
        template_prefix = '_'.join(subdirs) + '_'
    else:
        template_prefix = ''

    template_name = page.replace('.org', '.html')

    # First, try to find a template with the same name (s/.org/.html/) for the
    # page in the same folder
    try:
        return templates.get_template(template_prefix + template_name)
    except TemplateNotFound:
        pass

    # Else, try to use a default template on that folder
    try:
        return templates.get_template(template_prefix + DEFAULT_TEMPLATE)
    except TemplateNotFound:
        pass

    # If everything failed, use the default template in the root
    return templates.get_template(DEFAULT_TEMPLATE)


def _write_file(dest_file, template, template_options):
    """Render the given template to destination file"""
    
    with open(dest_file, 'w') as f:
        f.write(template.render(**template_options).encode('utf8'))


def _generate_index(output_dir, org_root, template, pages):

    index = Index(os.path.basename(output_dir), pages)

    index_path = os.path.join(output_dir, 'index.html')

    template_options = {
        'name': 'Itsahack!',
        'index': index,
        'root': org_root,
        }

    _write_file(index_path, template, template_options)

    return index

def _generate_page(fname, org_tree, org_root, output_dir, template, gen_options):
    """Generate the HTML for an org file and place it in the output"""

    html_file = os.path.splitext(fname)[0] + '.html'

    # generate the html for the org document
    html = org_to_html(org_tree[fname], **gen_options).decode('utf8')

    # create a page object
    # TODO: Use global options when these are not defined
    page = Page(org_tree[fname].options['TITLE'], \
                    html_file, \
                    org_tree[fname].options['AUTHOR'], \
                    org_tree[fname].options['DATE'], \
                    html)

    dest_file = os.path.join(output_dir, html_file)
    
    template_options = {
        'name': 'Itsahack!', 
        'page': page,
        'root': org_root,
        }

    _write_file(dest_file, template, template_options)

    return page

def _generate_pages(org_root, org_tree, output_dir, templates, files, folder, gen_options):
    """Generate the HTML of all files in a directory"""

    # Generate all pages in this directory
    pages = []
    for fname in files:

        # find the appropriate template for pages, based on the current folder
        page_template = _find_template(templates, folder, fname)

        page = _generate_page(fname, org_tree, org_root, output_dir, page_template, gen_options)
        pages.append(page)

    # If there is not an index.org in the directory, use the template
    if not 'index.org' in files:
        index_template = _find_template(templates, folder, INDEX_TEMPLATE)
        _generate_index(output_dir, org_root, index_template, pages)


def _make_tree(org_dir, org_tree, folder=''):
    """Traverse the directory tree, for each file in a tree node generate an org
    document.
    Arguments:
      org_dir: the base path of the org files
      org_tree: a dictionary where keys are filenames or subdir names, and
        values are either org documents or other dictionaries
      folder: the currently traversed folder
    """
    input_dir = os.path.join(org_dir, folder)
    dirs = os.listdir(input_dir)
    subdirs, files = _filter(dirs, \
                                 lambda d: \
                                 os.path.isdir(os.path.join(input_dir, d)))

    for fname in files:
        org_path = os.path.join(input_dir, fname)        

        with open(org_path, 'r') as org_file:
            org_doc = parser.parse(org_file)

        org_tree[fname] = org_doc

    for subdir in subdirs:
        newfolder = os.path.join(folder, subdir)
        org_tree[subdir] = {}
        _make_tree(org_dir, org_tree[subdir], newfolder)


def _traverse(org_root, org_tree, output_base, templates, gen_options, folder=''):
    """
    Arguments:
      org_root: a reference to the whole org document tree
      org_tree: the currently traversed subtree
      output_base: the base path of the destination
      templates: the templates directory
      gen_options: a dict with the options passed to the html generator
      folder: the currently traversed folder
    """
    output_dir = os.path.join(output_base, folder)

    # traverse the tree 
    files, subdirs = _filter(org_tree.keys(), \
                                 lambda k: \
                                 os.path.splitext(k)[1] == '.org')

    # generate the HTML for each org document in the current subdir
    _generate_pages(org_root, org_tree, output_dir, templates, files, folder, gen_options)

    # create each of the subdirs it in the output directory, then continue
    for subdir in subdirs:

        os.mkdir(os.path.join(output_dir, subdir))
        newfolder = os.path.join(folder, subdir)
        _traverse(org_root, org_tree[subdir], output_dir, templates, gen_options, newfolder)


def generate(input_dir, output_dir, gen_options):
    """Generate the site in input_dir to output_dir"""

    org = os.path.join(input_dir, ORG_DIR)
    templates = os.path.join(input_dir, TEMPLATES_DIR)
    media = os.path.join(input_dir, MEDIA_DIR)

    # first, create the tree with all the subdirs and org documents
    org_tree = {}
    _make_tree(org, org_tree)

    # create the template environment for jinja2
    t_env = Environment(loader= FileSystemLoader(templates, encoding='utf-8'))

    # traverse the tree and generate the corresponding HTML
    _traverse(org_tree, org_tree, output_dir, t_env, gen_options)

    # finally, copy the media folder to the output
    media_out = os.path.join(output_dir, MEDIA_DIR)
    if os.path.exists(media_out):
        shutil.rmtree(media_out)
    shutil.copytree(media, media_out)
    
if __name__ == '__main__':

    input_dir = None 
    output_dir = None
    level = 1

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'ho:l:i:')
    except getopt.GetoptError, err:
        usage()

    for opt, arg in opts:
        if opt == '-h':
            usage()

        elif opt == '-l':
            level = int(arg)

        elif opt == '-i':
            input_dir = arg

        elif opt == '-o':
            output_dir = arg

    if not output_dir or not input_dir:
        print 'Must provide input and output dir!'
        sys.exit(1)

    gen_options = {
        'remove_empty_p': True,
        'hl_offset': level,
        }

    generate(input_dir, output_dir, gen_options)
