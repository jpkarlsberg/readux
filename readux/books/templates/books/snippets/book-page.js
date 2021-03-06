{% load static %}

<script type="text/javascript" charset="utf-8">
   $(document).ready(function () {
      // set up seadragon configuration (not loaded unless triggered by user)
      set_seadragon_opts({
          id: "zoom-page",
          prefixUrl: "{% static 'js/openseadragon/images/' %}",
          tileSources: "{% url 'books:page-image' page.volume.pid page.pid 'info' %}",
          toolbar: 'deepzoom-controls',
          showNavigator: true,
          navigatorPosition: 'TOP_LEFT',
          zoomInButton: 'dz-zoom-in',
          zoomOutButton: 'dz-zoom-out',
          homeButton: 'dz-home',
          fullPageButton: 'dz-fs',
      });

      /* {# only enable annotation if tei is present for logged in users #} */
      {% if page.tei.exists and user.is_authenticated %}

      {% include 'books/snippets/annotator-init.js' with mode='full' volume_uri=page.volume.absolute_url %}

      {% endif %} {# end annotation config #}


      /* touch swipe navigation */
      // map swipe directions to navigation rel link attributes
      // currently using so-called "natural" directions to map
      // left/right to next/prev, e.g. as if turning a page or swiping
      // through a gallery
      var swipe_nav_rel = {
          'swiperight': 'prev',
          'swipeleft': 'next',
      };

      function swipeNav(direction) {
         if (direction in swipe_nav_rel) {
              var link = $('a[rel="' + swipe_nav_rel[direction] + '"]');
              if (link.length) {
                  window.location = link.first().attr('href');
              }
         }
      }
      // make sure text is still selectable within swipe area
      delete Hammer.defaults.cssProps.userSelect;
      // make image not draggable
      $('.page .content img').on('dragstart', function(event) { event.preventDefault(); });

      // Could bind to image only, but that seems to make swipe much
      // harder to use on text-heavy pages...
      var touch = new Hammer($('.page .content')[0]);
      // navigate to next/previous page on swipe left/right
      touch.on("swiperight swipeleft", function(ev) {
          swipeNav(ev.type);
      });
      // Could use pinch gesture to trigger zoom mode, but it makes it
      // impossible to scroll the page on smaller screens.  Would need
      // to be active only on a much smaller zone (e.g. control panel?)


   });
   {% if page.tei.exists %}
   // adjust ocr word & letter spacing on load & resize, with a timeout
   // to avoid adjusting too frequently as the browser is resized

      var resizeTimer; // Set resizeTimer to empty so it resets on page load
      function resizeFunction() {
          // adjust font sizes based on container to use viewport height
          $(".page img").relativeFontHeight({elements: $('.ocr-line')});
          // adjust ocr text on window load or resize
          $(".ocrtext").textwidth();
      };

      // On resize, run the function and reset the timeout with a 250ms delay
      $(window).resize(function() {
          clearTimeout(resizeTimer);
          resizeTimer = setTimeout(resizeFunction, 250);
      });

     $(window).load(function() {  // wait until load completes, so widths will be calculated
         resizeFunction();
     });
   {% endif %}
</script>
