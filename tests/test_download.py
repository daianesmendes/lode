from lode.etl.download import RemoteFile, parse_listing

LISTING = """<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:">
  <d:response>
    <d:href>/public.php/webdav/2026-10/</d:href>
    <d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat>
  </d:response>
  <d:response>
    <d:href>/public.php/webdav/2026-10/Cnaes.zip</d:href>
    <d:propstat><d:prop><d:getcontentlength>22078</d:getcontentlength></d:prop></d:propstat>
  </d:response>
  <d:response>
    <d:href>/public.php/webdav/2026-10/Empresas0.zip</d:href>
    <d:propstat><d:prop><d:getcontentlength>570972000</d:getcontentlength></d:prop></d:propstat>
  </d:response>
</d:multistatus>"""


def test_parse_listing_returns_files_with_sizes_and_skips_folders():
    assert parse_listing(LISTING) == [
        RemoteFile("Cnaes.zip", 22078),
        RemoteFile("Empresas0.zip", 570972000),
    ]
