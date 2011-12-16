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
import re
import os
import os.path
import shutil
import time
import datetime
import ConfigParser

from jinja2 import Environment, FileSystemLoader
from jinja2.exceptions import TemplateNotFound

from orgpython.parser import parser
from orgpython.export.html import org_to_html

DEFAULT_CONFIG = 'site.conf'

DATETIME_RE = r'<(\d{4})-(\d{2})-(\d{2}) [a-zA-Z]{3} (\d{2}):(\d{2})>'

def _parse_config(path):
    """Parse a configuration file and return a dictionary with the values"""

    site_defaults = { \
        'name': 'Default OrgSite',
        'default_template': 'default.html',
        'org': 'org',
        'media': 'media',
        'templates': 'templates',
        'alias': 'anon',
        'fullname': 'Anonymous',
        'hl_offset': 1,
        'remove_empty_p': True}

    config = ConfigParser.RawConfigParser(site_defaults)
    
    if not config.read(path):
        raise Exception("Could not find configuration file at %s" % path)

    values = {}
    for k in site_defaults:
        values[k] = config.get('org-site', k)

    # some casting
    values['hl_offset'] = int(values['hl_offset'])
    values['remove_empty_p'] = bool(values['remove_empty_p'])

    return values

def usage():

    print __doc__
    sys.exit(1)


class Site:
    """Information about the site"""
    def __init__(self, config):
        self.name = config['name']
        self.author_alias = config['alias']
        self.author_name = config['fullname']
        self.pages = {}


class Page:
    """A page is an org-mode text file"""
    def __init__(self, title, fname, date, html):
        self.title = title
        self.fname = fname
        self.html = html

        # Try to parse the date
        m = re.match(DATETIME_RE, date)
        if m:
            self.date = datetime.datetime(int(m.group(1)),
                                          int(m.group(2)),
                                          int(m.group(3)),
                                          int(m.group(4)),
                                          int(m.group(5)))
        else:
            self.date = date

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

def _find_template(templates, folder, page, default):
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
        return templates.get_template(template_prefix + default)
    except TemplateNotFound:
        pass

    # If everything failed, use the default template in the root
    return templates.get_template(default)


def _write_file(dest_file, template, template_options):
    """Render the given template to destination file"""
    
    with open(dest_file, 'w') as f:
        f.write(template.render(**template_options).encode('utf8'))


def _generate_page(fname, org_tree, output_dir, template, config, site):
    """Generate the HTML for an org file and place it in the output"""

    html_file = os.path.splitext(fname)[0] + '.html'

    # generate the html for the org document
    html = org_to_html(org_tree[fname], \
                           hl_offset=config['hl_offset'], \
                           remove_empty_p=config['remove_empty_p']).decode('utf8')

    # create a page object
    page = Page(org_tree[fname].options['TITLE'], \
                    html_file, \
                    org_tree[fname].options['DATE'], \
                    html)

    dest_file = os.path.join(output_dir, html_file)
    
    template_options = {
        'page': page,
        'site': site,
        }

    _write_file(dest_file, template, template_options)

    return page


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


def _traverse(org_root, org_tree, output_base, templates, config, site, folder=''):
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
    for fname in files:

        # find the appropriate template for pages, based on the current folder
        page_template = _find_template(templates, folder, fname, config['default_template'])
        _generate_page(fname, org_tree, output_dir, page_template, config, site)

    # create each of the subdirs it in the output directory, then continue
    for subdir in subdirs:

        os.mkdir(os.path.join(output_dir, subdir))
        newfolder = os.path.join(folder, subdir)
        _traverse(org_root, org_tree[subdir], output_dir, templates, config, site, newfolder)


def generate(input_dir, output_dir, config):
    """Generate the site in input_dir to output_dir"""

    org = os.path.join(input_dir, config['org'])
    templates = os.path.join(input_dir, config['templates'])
    media = os.path.join(input_dir, config['media'])

    # first, create the tree with all the subdirs and org documents
    org_tree = {}
    _make_tree(org, org_tree)

    # create the template environment for jinja2
    t_env = Environment(loader= FileSystemLoader(templates, encoding='utf-8'))

    # create the site object with the global information
    site = Site(config)

    # traverse the tree and generate the corresponding HTML
    _traverse(org_tree, org_tree, output_dir, t_env, config, site)

    # finally, copy the media folder to the output
    media_out = os.path.join(output_dir, config['media'])
    if os.path.exists(media_out):
        shutil.rmtree(media_out)
    shutil.copytree(media, media_out)
    
if __name__ == '__main__':

    input_dir = None 
    output_dir = None
    configuration = DEFAULT_CONFIG

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'ho:i:c:')
    except getopt.GetoptError, err:
        usage()

    for opt, arg in opts:
        if opt == '-h':
            usage()

        elif opt == '-i':
            input_dir = arg

        elif opt == '-o':
            output_dir = arg

        elif opt == '-c':
            configuration = arg

    if not output_dir or not input_dir:
        print 'Must provide input and output dir!'
        sys.exit(1)

    try:
        config = _parse_config(configuration)
    except Exception as e:
        print "Configuration error: %s" % e
        sys.exit(1)

    generate(input_dir, output_dir, config)
