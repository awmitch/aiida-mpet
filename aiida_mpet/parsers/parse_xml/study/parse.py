# -*- coding: utf-8 -*-
from xmlschema.etree import ElementTree

from aiida_mpet.parsers.parse_xml.exceptions import XMLParseError
from aiida_mpet.parsers.parse_xml.versions import get_xml_file_version, QeXmlVersion
from aiida_mpet.parsers.parse_xml.parse import parse_xml_post_6_2

from .legacy import parse_mpetrun_xml_pre_6_2


def parse_xml(xml_file, dir_with_bands=None):
    try:
        xml_parsed = ElementTree.parse(xml_file)
    except ElementTree.ParseError:
        raise XMLParseError('error while parsing XML file')

    xml_file_version = get_xml_file_version(xml_parsed)

    if xml_file_version == QeXmlVersion.POST_6_2:
        parsed_data, logs = parse_xml_post_6_2(xml_parsed)
    elif xml_file_version == QeXmlVersion.PRE_6_2:
        xml_file.seek(0)
        parsed_data, logs = parse_mpetrun_xml_pre_6_2(xml_file, dir_with_bands)

    return parsed_data, logs
