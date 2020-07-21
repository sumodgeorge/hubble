# -*- coding: utf-8 -*-
'''
Tests for hubblestack.utils.data
'''

# Import Python libs
from __future__ import absolute_import, print_function, unicode_literals
import logging
import builtins

# Import Salt libs
import hubblestack.utils.data
import hubblestack.utils.stringutils
from hubblestack.utils.odict import OrderedDict
from tests.support.unit import TestCase, skipIf, LOREM_IPSUM
from tests.support.mock import patch, NO_MOCK, NO_MOCK_REASON

log = logging.getLogger(__name__)
_b = lambda x: x.encode('utf-8')
_s = lambda x: hubblestack.utils.stringutils.to_str(x, normalize=True)
# Some randomized data that will not decode
BYTES = b'1\x814\x10'

# This is an example of a unicode string with й constructed using two separate
# code points. Do not modify it.
EGGS = '\u044f\u0438\u0306\u0446\u0430'


class DataTestCase(TestCase):
    test_data = [
        'unicode_str',
        _b('питон'),
        123,
        456.789,
        True,
        False,
        None,
        EGGS,
        BYTES,
        [123, 456.789, _b('спам'), True, False, None, EGGS, BYTES],
        (987, 654.321, _b('яйца'), EGGS, None, (True, EGGS, BYTES)),
        {_b('str_key'): _b('str_val'),
         None: True,
         123: 456.789,
         EGGS: BYTES,
         _b('subdict'): {'unicode_key': EGGS,
                         _b('tuple'): (123, 'hello', _b('world'), True, EGGS, BYTES),
                         _b('list'): [456, _b('спам'), False, EGGS, BYTES]}},
        OrderedDict([(_b('foo'), 'bar'), (123, 456), (EGGS, BYTES)])
    ]

    def test_traverse_dict_and_list(self):
        test_two_level_dict = {'foo': {'bar': 'baz'}}
        test_two_level_dict_and_list = {
            'foo': ['bar', 'baz', {'lorem': {'ipsum': [{'dolor': 'sit'}]}}]
        }

        # Check traversing too far: hubblestack.utils.data.traverse_dict_and_list() returns
        # the value corresponding to a given key path, and baz is a value
        # corresponding to the key path foo:bar.
        self.assertDictEqual(
            {'not_found': 'nope'},
            hubblestack.utils.data.traverse_dict_and_list(
                test_two_level_dict, 'foo:bar:baz', {'not_found': 'nope'}
            )
        )
        # Now check to ensure that foo:bar corresponds to baz
        self.assertEqual(
            'baz',
            hubblestack.utils.data.traverse_dict_and_list(
                test_two_level_dict, 'foo:bar', {'not_found': 'not_found'}
            )
        )
        # Check traversing too far
        self.assertDictEqual(
            {'not_found': 'nope'},
            hubblestack.utils.data.traverse_dict_and_list(
                test_two_level_dict_and_list, 'foo:bar', {'not_found': 'nope'}
            )
        )
        # Check index 1 (2nd element) of list corresponding to path 'foo'
        self.assertEqual(
            'baz',
            hubblestack.utils.data.traverse_dict_and_list(
                test_two_level_dict_and_list, 'foo:1', {'not_found': 'not_found'}
            )
        )
        # Traverse a couple times into dicts embedded in lists
        self.assertEqual(
            'sit',
            hubblestack.utils.data.traverse_dict_and_list(
                test_two_level_dict_and_list,
                'foo:lorem:ipsum:dolor',
                {'not_found': 'not_found'}
            )
        )

    def test_compare_dicts(self):
        ret = hubblestack.utils.data.compare_dicts(old={'foo': 'bar'}, new={'foo': 'bar'})
        self.assertEqual(ret, {})

        ret = hubblestack.utils.data.compare_dicts(old={'foo': 'bar'}, new={'foo': 'woz'})
        expected_ret = {'foo': {'new': 'woz', 'old': 'bar'}}
        self.assertDictEqual(ret, expected_ret)

    def test_decode(self):
        '''
        Companion to test_decode_to_str, they should both be kept up-to-date
        with one another.

        NOTE: This uses the lambda "_b" defined above in the global scope,
        which encodes a string to a bytestring, assuming utf-8.
        '''
        expected = [
            'unicode_str',
            'питон',
            123,
            456.789,
            True,
            False,
            None,
            'яйца',
            BYTES,
            [123, 456.789, 'спам', True, False, None, 'яйца', BYTES],
            (987, 654.321, 'яйца', 'яйца', None, (True, 'яйца', BYTES)),
            {'str_key': 'str_val',
             None: True,
             123: 456.789,
             'яйца': BYTES,
             'subdict': {'unicode_key': 'яйца',
                         'tuple': (123, 'hello', 'world', True, 'яйца', BYTES),
                         'list': [456, 'спам', False, 'яйца', BYTES]}},
            OrderedDict([('foo', 'bar'), (123, 456), ('яйца', BYTES)])
        ]

        ret = hubblestack.utils.data.decode(
            self.test_data,
            keep=True,
            normalize=True,
            preserve_dict_class=True,
            preserve_tuples=True)
        self.assertEqual(ret, expected)

        # The binary data in the data structure should fail to decode, even
        # using the fallback, and raise an exception.
        self.assertRaises(
            UnicodeDecodeError,
            hubblestack.utils.data.decode,
            self.test_data,
            keep=False,
            normalize=True,
            preserve_dict_class=True,
            preserve_tuples=True)

        # Now munge the expected data so that we get what we would expect if we
        # disable preservation of dict class and tuples
        expected[10] = [987, 654.321, 'яйца', 'яйца', None, [True, 'яйца', BYTES]]
        expected[11]['subdict']['tuple'] = [123, 'hello', 'world', True, 'яйца', BYTES]
        expected[12] = {'foo': 'bar', 123: 456, 'яйца': BYTES}

        ret = hubblestack.utils.data.decode(
            self.test_data,
            keep=True,
            normalize=True,
            preserve_dict_class=False,
            preserve_tuples=False)
        self.assertEqual(ret, expected)

        # Now test single non-string, non-data-structure items, these should
        # return the same value when passed to this function
        for item in (123, 4.56, True, False, None):
            log.debug('Testing decode of %s', item)
            self.assertEqual(hubblestack.utils.data.decode(item), item)

        # Test single strings (not in a data structure)
        self.assertEqual(hubblestack.utils.data.decode('foo'), 'foo')
        self.assertEqual(hubblestack.utils.data.decode(_b('bar')), 'bar')
        self.assertEqual(hubblestack.utils.data.decode(EGGS, normalize=True), 'яйца')
        self.assertEqual(hubblestack.utils.data.decode(EGGS, normalize=False), EGGS)

        # Test binary blob
        self.assertEqual(hubblestack.utils.data.decode(BYTES, keep=True), BYTES)
        self.assertRaises(
            UnicodeDecodeError,
            hubblestack.utils.data.decode,
            BYTES,
            keep=False)

    def test_decode_to_str(self):
        '''
        Companion to test_decode, they should both be kept up-to-date with one
        another.

        NOTE: This uses the lambda "_s" defined above in the global scope,
        which converts the string/bytestring to a str type.
        '''
        expected = [
            _s('unicode_str'),
            _s('питон'),
            123,
            456.789,
            True,
            False,
            None,
            _s('яйца'),
            BYTES,
            [123, 456.789, _s('спам'), True, False, None, _s('яйца'), BYTES],
            (987, 654.321, _s('яйца'), _s('яйца'), None, (True, _s('яйца'), BYTES)),
            {_s('str_key'): _s('str_val'),
             None: True,
             123: 456.789,
             _s('яйца'): BYTES,
             _s('subdict'): {
                 _s('unicode_key'): _s('яйца'),
                 _s('tuple'): (123, _s('hello'), _s('world'), True, _s('яйца'), BYTES),
                 _s('list'): [456, _s('спам'), False, _s('яйца'), BYTES]}},
            OrderedDict([(_s('foo'), _s('bar')), (123, 456), (_s('яйца'), BYTES)])
        ]

        ret = hubblestack.utils.data.decode(
            self.test_data,
            keep=True,
            normalize=True,
            preserve_dict_class=True,
            preserve_tuples=True,
            to_str=True)
        self.assertEqual(ret, expected)

        # The binary data in the data structure should fail to decode, even
        # using the fallback, and raise an exception.
        self.assertRaises(
            UnicodeDecodeError,
            hubblestack.utils.data.decode,
            self.test_data,
            keep=False,
            normalize=True,
            preserve_dict_class=True,
            preserve_tuples=True,
            to_str=True)

        # Now munge the expected data so that we get what we would expect if we
        # disable preservation of dict class and tuples
        expected[10] = [987, 654.321, _s('яйца'), _s('яйца'), None, [True, _s('яйца'), BYTES]]
        expected[11][_s('subdict')][_s('tuple')] = [123, _s('hello'), _s('world'), True, _s('яйца'), BYTES]
        expected[12] = {_s('foo'): _s('bar'), 123: 456, _s('яйца'): BYTES}

        ret = hubblestack.utils.data.decode(
            self.test_data,
            keep=True,
            normalize=True,
            preserve_dict_class=False,
            preserve_tuples=False,
            to_str=True)
        self.assertEqual(ret, expected)

        # Now test single non-string, non-data-structure items, these should
        # return the same value when passed to this function
        for item in (123, 4.56, True, False, None):
            log.debug('Testing decode of %s', item)
            self.assertEqual(hubblestack.utils.data.decode(item, to_str=True), item)

        # Test single strings (not in a data structure)
        self.assertEqual(hubblestack.utils.data.decode('foo', to_str=True), _s('foo'))
        self.assertEqual(hubblestack.utils.data.decode(_b('bar'), to_str=True), _s('bar'))

        # Test binary blob
        self.assertEqual(
            hubblestack.utils.data.decode(BYTES, keep=True, to_str=True),
            BYTES
        )
        self.assertRaises(
            UnicodeDecodeError,
            hubblestack.utils.data.decode,
            BYTES,
            keep=False,
            to_str=True)

    @skipIf(NO_MOCK, NO_MOCK_REASON)
    def test_decode_fallback(self):
        '''
        Test fallback to utf-8
        '''
        with patch.object(builtins, '__salt_system_encoding__', 'ascii'):
            self.assertEqual(hubblestack.utils.data.decode(_b('яйца')), 'яйца')

    def test_encode(self):
        '''
        NOTE: This uses the lambda "_b" defined above in the global scope,
        which encodes a string to a bytestring, assuming utf-8.
        '''
        expected = [
            _b('unicode_str'),
            _b('питон'),
            123,
            456.789,
            True,
            False,
            None,
            _b(EGGS),
            BYTES,
            [123, 456.789, _b('спам'), True, False, None, _b(EGGS), BYTES],
            (987, 654.321, _b('яйца'), _b(EGGS), None, (True, _b(EGGS), BYTES)),
            {_b('str_key'): _b('str_val'),
             None: True,
             123: 456.789,
             _b(EGGS): BYTES,
             _b('subdict'): {_b('unicode_key'): _b(EGGS),
                             _b('tuple'): (123, _b('hello'), _b('world'), True, _b(EGGS), BYTES),
                             _b('list'): [456, _b('спам'), False, _b(EGGS), BYTES]}},
             OrderedDict([(_b('foo'), _b('bar')), (123, 456), (_b(EGGS), BYTES)])
        ]

        # Both keep=True and keep=False should work because the BYTES data is
        # already bytes.
        ret = hubblestack.utils.data.encode(
            self.test_data,
            keep=True,
            preserve_dict_class=True,
            preserve_tuples=True)
        self.assertEqual(ret, expected)
        ret = hubblestack.utils.data.encode(
            self.test_data,
            keep=False,
            preserve_dict_class=True,
            preserve_tuples=True)
        self.assertEqual(ret, expected)

        # Now munge the expected data so that we get what we would expect if we
        # disable preservation of dict class and tuples
        expected[10] = [987, 654.321, _b('яйца'), _b(EGGS), None, [True, _b(EGGS), BYTES]]
        expected[11][_b('subdict')][_b('tuple')] = [
            123, _b('hello'), _b('world'), True, _b(EGGS), BYTES
        ]
        expected[12] = {_b('foo'): _b('bar'), 123: 456, _b(EGGS): BYTES}

        ret = hubblestack.utils.data.encode(
            self.test_data,
            keep=True,
            preserve_dict_class=False,
            preserve_tuples=False)
        self.assertEqual(ret, expected)
        ret = hubblestack.utils.data.encode(
            self.test_data,
            keep=False,
            preserve_dict_class=False,
            preserve_tuples=False)
        self.assertEqual(ret, expected)

        # Now test single non-string, non-data-structure items, these should
        # return the same value when passed to this function
        for item in (123, 4.56, True, False, None):
            log.debug('Testing encode of %s', item)
            self.assertEqual(hubblestack.utils.data.encode(item), item)

        # Test single strings (not in a data structure)
        self.assertEqual(hubblestack.utils.data.encode('foo'), _b('foo'))
        self.assertEqual(hubblestack.utils.data.encode(_b('bar')), _b('bar'))

        # Test binary blob, nothing should happen even when keep=False since
        # the data is already bytes
        self.assertEqual(hubblestack.utils.data.encode(BYTES, keep=True), BYTES)
        self.assertEqual(hubblestack.utils.data.encode(BYTES, keep=False), BYTES)

    def test_encode_keep(self):
        '''
        Whereas we tested the keep argument in test_decode, it is much easier
        to do a more comprehensive test of keep in its own function where we
        can force the encoding.
        '''
        unicode_str = 'питон'
        encoding = 'ascii'

        # Test single string
        self.assertEqual(
            hubblestack.utils.data.encode(unicode_str, encoding, keep=True),
            unicode_str)
        self.assertRaises(
            UnicodeEncodeError,
            hubblestack.utils.data.encode,
            unicode_str,
            encoding,
            keep=False)

        data = [
            unicode_str,
            [b'foo', [unicode_str], {b'key': unicode_str}, (unicode_str,)],
            {b'list': [b'foo', unicode_str],
             b'dict': {b'key': unicode_str},
             b'tuple': (b'foo', unicode_str)},
            ([b'foo', unicode_str], {b'key': unicode_str}, (unicode_str,))
        ]

        # Since everything was a bytestring aside from the bogus data, the
        # return data should be identical. We don't need to test recursive
        # decoding, that has already been tested in test_encode.
        self.assertEqual(
            hubblestack.utils.data.encode(data, encoding,
                                   keep=True, preserve_tuples=True),
            data
        )
        self.assertRaises(
            UnicodeEncodeError,
            hubblestack.utils.data.encode,
            data,
            encoding,
            keep=False,
            preserve_tuples=True)

        for index, item in enumerate(data):
            self.assertEqual(
                hubblestack.utils.data.encode(data[index], encoding,
                                       keep=True, preserve_tuples=True),
                data[index]
            )
            self.assertRaises(
                UnicodeEncodeError,
                hubblestack.utils.data.encode,
                data[index],
                encoding,
                keep=False,
                preserve_tuples=True)

    @skipIf(NO_MOCK, NO_MOCK_REASON)
    def test_encode_fallback(self):
        '''
        Test fallback to utf-8
        '''
        with patch.object(builtins, '__salt_system_encoding__', 'ascii'):
            self.assertEqual(hubblestack.utils.data.encode('яйца'), _b('яйца'))
        with patch.object(builtins, '__salt_system_encoding__', 'CP1252'):
            self.assertEqual(hubblestack.utils.data.encode('Ψ'), _b('Ψ'))

    def test_repack_dict(self):
        list_of_one_element_dicts = [{'dict_key_1': 'dict_val_1'},
                                     {'dict_key_2': 'dict_val_2'},
                                     {'dict_key_3': 'dict_val_3'}]
        expected_ret = {'dict_key_1': 'dict_val_1',
                        'dict_key_2': 'dict_val_2',
                        'dict_key_3': 'dict_val_3'}
        ret = hubblestack.utils.data.repack_dictlist(list_of_one_element_dicts)
        self.assertDictEqual(ret, expected_ret)

        # Try with yaml
        yaml_key_val_pair = '- key1: val1'
        ret = hubblestack.utils.data.repack_dictlist(yaml_key_val_pair)
        self.assertDictEqual(ret, {'key1': 'val1'})

        # Make sure we handle non-yaml junk data
        ret = hubblestack.utils.data.repack_dictlist(LOREM_IPSUM)
        self.assertDictEqual(ret, {})

    def test_stringify(self):
        self.assertRaises(TypeError, hubblestack.utils.data.stringify, 9)
        self.assertEqual(
            hubblestack.utils.data.stringify(['one', 'two', str('three'), 4, 5]),  # future lint: disable=blacklisted-function
            ['one', 'two', 'three', '4', '5']
        )
