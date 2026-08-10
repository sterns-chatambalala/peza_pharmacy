from django.contrib.sitemaps import Sitemap
from django.urls import reverse

class StaticViewSitemap(Sitemap):
    priority = 0.5
    changefreq = 'daily'

    def items(self):
        return ['landing_page', 'login', 'register', 'forgot_password']

    def location(self, item):
        return reverse(item)
