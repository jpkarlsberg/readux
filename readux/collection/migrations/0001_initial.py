# -*- coding: utf-8 -*-
from south.utils import datetime_utils as datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Adding model 'CollectionImage'
        db.create_table(u'collection_collectionimage', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('collection', self.gf('django.db.models.fields.CharField')(unique=True, max_length=255)),
            ('cover', self.gf('django.db.models.fields.related.ForeignKey')(related_name='coverimage_set', to=orm['django_image_tools.Image'])),
            ('banner', self.gf('django.db.models.fields.related.ForeignKey')(blank=True, related_name='bannerimage_set', null=True, to=orm['django_image_tools.Image'])),
        ))
        db.send_create_signal(u'collection', ['CollectionImage'])


    def backwards(self, orm):
        # Deleting model 'CollectionImage'
        db.delete_table(u'collection_collectionimage')


    models = {
        u'collection.collectionimage': {
            'Meta': {'object_name': 'CollectionImage'},
            'banner': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'bannerimage_set'", 'null': 'True', 'to': u"orm['django_image_tools.Image']"}),
            'collection': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '255'}),
            'cover': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'coverimage_set'", 'to': u"orm['django_image_tools.Image']"}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'})
        },
        u'django_image_tools.image': {
            'Meta': {'object_name': 'Image'},
            'alt_text': ('django.db.models.fields.CharField', [], {'max_length': '120'}),
            'caption': ('django.db.models.fields.TextField', [], {}),
            'checksum': ('django.db.models.fields.CharField', [], {'max_length': '32'}),
            'credit': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'filename': ('django.db.models.fields.SlugField', [], {'max_length': '50'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'image': ('django.db.models.fields.files.ImageField', [], {'max_length': '100'}),
            'subject_position_horizontal': ('django.db.models.fields.PositiveSmallIntegerField', [], {'default': '2'}),
            'subject_position_vertical': ('django.db.models.fields.PositiveSmallIntegerField', [], {'default': '2'}),
            'title': ('django.db.models.fields.CharField', [], {'max_length': '120'}),
            'was_upscaled': ('django.db.models.fields.BooleanField', [], {'default': 'False'})
        }
    }

    complete_apps = ['collection']