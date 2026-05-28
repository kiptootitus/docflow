"""
DocFlow AI — docflow/pagination.py

Custom pagination class that overrides DRF's CursorPagination default
ordering of '-created' (which doesn't exist) with '-created_at'.
"""

from rest_framework.pagination import CursorPagination


class StandardCursorPagination(CursorPagination):
    page_size          = 20
    page_size_query_param = "page_size"
    max_page_size      = 100
    ordering           = "-created_at"