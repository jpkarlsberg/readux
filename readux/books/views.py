from django.conf import settings
from django.core.paginator import Paginator, EmptyPage, InvalidPage
from django.http import Http404, HttpResponse, HttpResponseNotFound
from django.shortcuts import render
from django.views.decorators.http import condition, require_http_methods, \
   last_modified
from urllib import urlencode
import os

from eulfedora.server import Repository, RequestFailed
from eulfedora.views import raw_datastream

from readux.books.models import Volume, VolumeV1_0, SolrVolume, Page, PageV1_0
from readux.books.forms import BookSearch
from readux.books import view_helpers
from readux.utils import solr_interface


@last_modified(view_helpers.volumes_modified)
def search(request, mode='list'):

    form = BookSearch(request.GET)
    context = {'form': form}

    if form.is_valid():
        # get list of keywords and phrases
        terms = form.search_terms()
        solr = solr_interface()
        # generate queries text and boost-field queries
        text_query = solr.Q()
        author_query = solr.Q()
        title_query = solr.Q()
        for t in terms:
            text_query |= solr.Q(t)
            author_query |= solr.Q(creator=t)
            title_query |= solr.Q(title=t)

        q = solr.query().filter(content_model=Volume.VOLUME_CMODEL_PATTERN) \
                .query(text_query | author_query**3 | title_query**3) \
                .field_limit(SolrVolume.necessary_fields, score=True)  \
                .results_as(SolrVolume) \
                .sort_by('-score')

        # don't need to facet on collection if we are already filtered on collection
        if 'collection' not in request.GET:
            q = q.facet_by('collection_label_facet', sort='index', mincount=1)

        # TODO: how can we determine via solr query if a volume has pages loaded?
        # join query on pages? index page_count in solr?

        # url parameters for pagination and facet links
        url_params = request.GET.copy()

        # generate list for display and removal of active filters
        display_filters = []
        if 'collection' in request.GET:
            filter_val = request.GET['collection']
            # filter the solr query based on the requested collection
            q = q.query(collection_label='"%s"' % filter_val)
            # generate link to remove the facet
            unfacet_urlopts = url_params.copy()
            del unfacet_urlopts['collection']
            display_filters.append(('collection', filter_val,
                                    unfacet_urlopts.urlencode()))

        # paginate the solr result set
        paginator = Paginator(q, 30)
        try:
            page = int(request.GET.get('page', '1'))
        except ValueError:
            page = 1
        try:
            results = paginator.page(page)
        except (EmptyPage, InvalidPage):
            results = paginator.page(paginator.num_pages)

        if 'page' in url_params:
            del url_params['page']

        # adjust facets as returned from solr for diplay
        facet_fields = results.object_list.facet_counts.facet_fields
        facets = {
            'collection': facet_fields.get('collection_label_facet', []),
        }

        context.update({
            'items': results,
            'url_params': urlencode(url_params),
            'facets': facets,  # available facets
            'filters': display_filters,  # active filters
            'mode': mode,  # list / cover view
            'current_url_params': urlencode(request.GET.copy())

        })

    return render(request, 'books/search.html', context)


@last_modified(view_helpers.volume_modified)
def volume(request, pid):
    ''' Landing page for a single :class:`~readux.books.models.Volume`.

    If keyword search terms are specified, searches within the book and
    finds matching pages.
    '''

    repo = Repository()
    vol = repo.get_object(pid, type=Volume)
    if not vol.exists or not vol.has_requisite_content_models:
        raise Http404

    form = BookSearch(request.GET)
    context = {'vol': vol, 'form': form}
    template = 'books/volume.html'

    # if form is valid, then search within the book and display matching pages
    # instead of volume info
    if form.is_valid():
        terms = form.search_terms()

        solr = solr_interface()
        query = solr.Q()
        for t in terms:
            # NOTE: should this be OR or AND?
            query |= solr.Q(page_text=t)
        # search for pages that belong to this book
        q = solr.query().filter(content_model=PageV1_0.PAGE_CONTENT_MODEL,
                                isConstituentOf=vol.uri) \
                .query(query) \
                .field_limit(['page_order', 'pid'], score=True) \
                .highlight('page_text', snippets=3) \
                .sort_by('-score').sort_by('page_order')
        # return highlighted snippets from page text
        # sort by relevance and then by page order

        # paginate the solr result set
        paginator = Paginator(q, 30)
        try:
            page = int(request.GET.get('page', '1'))
        except ValueError:
            page = 1
        try:
            results = paginator.page(page)
        except (EmptyPage, InvalidPage):
            results = paginator.page(paginator.num_pages)

        # url parameters for pagination
        url_params = request.GET.copy()
        if 'page' in url_params:
            del url_params['page']

        # uses a different template than volume display
        template = 'books/volume_search.html'
        context.update({
            'pages': results,
            'url_params': urlencode(url_params),
        })

    return render(request, template, context)


@last_modified(view_helpers.volume_pages_modified)
def volume_pages(request, pid):
    # paginated thumbnails for all pages in a book
    repo = Repository()
    vol = repo.get_object(pid, type=Volume)
    if not vol.exists or not vol.has_requisite_content_models:
        raise Http404
    # search for page images in solr so we can easily sort by order
    pagequery = vol.find_solr_pages()

    # paginate pages, 30 per page
    per_page = 30
    paginator = Paginator(pagequery, per_page, orphans=5)

    try:
        page = int(request.GET.get('page', '1'))
    except ValueError:
        page = 1
    try:
        results = paginator.page(page)
    except (EmptyPage, InvalidPage):
        results = paginator.page(paginator.num_pages)

    # form for searching in this book
    form = BookSearch()

    return render(request, 'books/pages.html',
        {'vol': vol, 'pages': results, 'form': form})


@last_modified(view_helpers.page_modified)
def view_page(request, pid):
    repo = Repository()
    page = repo.get_object(pid, type=Page)
    if not page.exists or not page.has_requisite_content_models:
        raise Http404

    # use solr to find adjacent pages to this one
    pagequery = page.volume.find_solr_pages()
    # search range around current page order
    # (+/-1 should probably work, but using 2 to allow some margin for error)
    pagequery = pagequery.query(page_order__range=(page.page_order - 2,
                                                   page.page_order + 2))

    # find the index of the current page in the sorted solr result
    index = 0
    prev = nxt = None
    for p in pagequery:
        if p['pid'] == page.pid:
            break
        index += 1
        prev = p

    if len(pagequery) > index + 1:
        nxt = pagequery[index + 1]

    # calculates which paginated page the page is part of based on 30 items per page
    page_chunk = ((page.page_order - 1) // 30) + 1

    # form for searching in this book
    form = BookSearch()

    return render(request, 'books/page.html',
        {'page': page, 'next': nxt, 'prev': prev, 'page_chunk':page_chunk,
         'form': form})



@condition(etag_func=view_helpers.pdf_etag, last_modified_func=view_helpers.pdf_lastmodified)
def pdf(request, pid):
    '''View to allow access to the PDF datastream of a
    :class:`~readux.books.models.Volume` object.  Sets a
    content-disposition header that will prompt the file to be saved
    with a default title based on the object label.
    '''
    repo = Repository()
    try:
        # retrieve the object so we can use it to set the download filename
        obj = repo.get_object(pid, type=Volume)
        extra_headers = {
            # generate a default filename based on the object label
            'Content-Disposition': 'filename="%s.pdf"' % obj.label.replace(' ', '-')
        }
        # use generic raw datastream view from eulfedora
        return raw_datastream(request, pid, Volume.pdf.id, type=Volume,
            repo=repo, headers=extra_headers)
    except RequestFailed:
        raise Http404


@condition(etag_func=view_helpers.ocr_etag, last_modified_func=view_helpers.ocr_lastmodified)
def ocr(request, pid):
    '''View to allow access the raw OCR xml datastream of a
    :class:`~readux.books.models.Volume` object.
    '''
    repo = Repository()
    # use generic raw datastream view from eulfedora
    return raw_datastream(request, pid, Volume.ocr.id, type=Volume,
        repo=repo)


@condition(etag_func=view_helpers.ocr_etag, last_modified_func=view_helpers.ocr_lastmodified)
def text(request, pid):
    '''View to allow access the plain text content of a
    :class:`~readux.books.models.Volume` object.
    '''
    repo = Repository()
    obj = repo.get_object(pid, type=Volume)
    # if object doesn't exist, isn't a volume, or doesn't have ocr text - 404
    if not obj.exists or not obj.has_requisite_content_models or not obj.ocr.exists:
        raise Http404

    response = HttpResponse(obj.get_fulltext(), 'text/plain')
    # generate a default filename based on the object label
    response['Content-Disposition'] = 'filename="%s.txt"' % obj.label.replace(' ', '-')
    return response


@condition(etag_func=view_helpers.unapi_etag, last_modified_func=view_helpers.unapi_modified)
def unapi(request):
    '''unAPI service point for :class:`~readux.books.models.Volume` objects,
    to make content available for harvest via Zotero.'''

    # NOTE: this could probably be generalized into a re-usable view
    # (maybe an extensible class-based view?) for re-use

    item_id = request.GET.get('id', None)
    fmt = request.GET.get('format', None)
    context = {}
    if item_id is not None:
        context['id'] = item_id
        repo = Repository(request=request)
        # generalized class-based view would need probably a get-item method
        # for repo objects, could use type-inferring repo variant
        obj = repo.get_object(item_id, type=Volume)

        formats = obj.unapi_formats

        if fmt is None:
            # display formats for this item
            context['formats'] = formats
        else:
            current_format = formats[fmt]
            # return requested format for this item
            meth = getattr(obj, current_format['method'])
            return HttpResponse(meth(), content_type=current_format['type'])

    else:
        # display formats for all items
        # NOTE: if multiple classes, should be able to combine the formats
        context['formats'] = Volume.unapi_formats

    # NOTE: doesn't really even need to be a template, could be generated
    # with eulxml just as easily if that simplifies reuse
    return render(request, 'books/unapi_format.xml', context,
        content_type='application/xml')


def _error_image_response(mode):
    # error image http response for 401/404/500 errors when serving out
    # images from fedora
    error_images = {
        'thumbnail': 'notfound_thumbnail.png',
        'single-page': 'notfound_page.png',
        'mini-thumbnail': 'notfound_mini_thumbnail_page.png',
    }
    # need a different way to catch it
    if mode in error_images:
        img = error_images[mode]

        if settings.DEBUG:
            base_path = settings.STATICFILES_DIRS[0]
        else:
            base_path = settings.STATIC_ROOT
        with open(os.path.join(base_path, 'img', img)) as content:
            return HttpResponseNotFound(content.read(), mimetype='image/png')

@require_http_methods(['GET', 'HEAD'])
@condition(etag_func=view_helpers.page_image_etag,
           last_modified_func=view_helpers.page_image_lastmodified)
def page_image(request, pid, mode=None):
    '''Return a page image, resized according to mode.

    :param pid: the pid of the :class:`~readux.books.models.Page`
        object
    :param mode: image mode (used to determine image size to return);
        currently one of thumbnail, singe-page, or fullsize
    '''
    try:
        repo = Repository()
        page = repo.get_object(pid, type=Page)
        if page.image.exists:
            # Explicitly support HEAD for efficiency (skip API call)
            if request.method == 'HEAD':
                content = ''
            else:
                if mode == 'thumbnail':
                    content = page.get_region(scale=300)
                elif mode == 'mini-thumbnail':
                    # mini thumbnail for list view - try 100x100 or 120x120
                    content = page.get_region(level=1, scale=100)
                    # NOTE: this works, but doesn't consistently get centered content
                    # content = page.get_region(level='1', region='0,0,100,100')
                elif mode == 'single-page':
                    # NOTE: using get_region instead of get_region_chunks here
                    # to make it possible to catch the error and serve out
                    # an error image; page images at this size shouldn't
                    # be large enough to really need chunking
                    content = page.get_region(scale=1000)
                    # content = page.get_region_chunks(scale=1000)
                elif mode == 'fullsize':
                    content = page.get_region_chunks(level='') # default (max) level

            return HttpResponse(content, mimetype='image/jpeg')
            # NOTE: last-modified and etag headers are set on the response
            # by the django condition decorator methods

            # NOTE: some overlap in headers/error checking with
            # eulfedora.views.raw_datastream
            # Consider pulling out common functionality, or writing
            # another generic eulfedora view for serving out
            # datastream-based dissemination content

        else:
            # 404 if the page image doesn't exist
            # - 404 with error image if in a supported mode
            response = _error_image_response(mode)
            if response:
                return response
            else:
                raise Http404

    except RequestFailed as rf:
        # generate error image response, if in a supported mode
        response = _error_image_response(mode)
        if response:
            # update response status code to match fedora error
            # (401, 404, or 500)
            response.status_code = rf.code
            return response

        if rf.code in [404, 401]:
            raise Http404
        raise
