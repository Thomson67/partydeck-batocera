"""Windows metadata references, safe matching, live import and existing entries."""
import os
os.environ['PARTYDECK_LANGUAGE']='fr'
import sys
from pathlib import Path
from unittest.mock import Mock,patch
import tempfile
import xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import partydeck_profiles as profiles
from partydeck_i18n import set_language,tr

with tempfile.TemporaryDirectory() as temp:
    root=Path(temp);windows=root/'windows';windows.mkdir();party=root/'windows-party';party.mkdir()
    base=root/'system';base.mkdir()
    game=windows/'Sous dossier/Jeu & test.wsquashfs';game.parent.mkdir();game.write_bytes(b'ROM')
    entry=party/'Jeu [abc].sh'
    entry.write_text('#!/bin/bash\n'+profiles.MARKER+'\nexec '+__import__('shlex').join([str(base/'windows-party'),'profil',str(game)])+'\n')
    src=windows/'gamelist.xml'
    source=ET.Element('gameList');g=ET.SubElement(source,'game',id='original')
    fields={'path':'./Sous dossier/Jeu & test.wsquashfs','name':'Titre propre','desc':'Texte & accents é',
        'image':'./images/jeu.png','video':'./videos/jeu.mp4','manual':'./manuals/jeu.pdf',
        'thumbnail':str(root/'external/box.png'),'marquee':'https://example.test/logo.png',
        'rating':'0.8','developer':'Studio','players':'1-4','favorite':'false','playcount':'400','hidden':'true'}
    for k,v in fields.items():ET.SubElement(g,k).text=v
    ET.ElementTree(source).write(src,encoding='utf-8')
    solo_before=src.read_bytes()
    dest=party/'gamelist.xml'
    dest.write_text('<gameList><game><path>./Configurer Windows Party.sh</path><name>Menu</name></game><game><path>./Jeu [abc].sh</path><favorite>true</favorite><playcount>3</playcount><lastplayed>20261118</lastplayed><custom>keep</custom></game></gameList>')
    destination_before=dest.read_bytes()
    assert profiles.sync_library_scrapes(base,party)==1
    saved=ET.parse(dest).getroot();out=saved.findall('game')[1]
    assert len(saved.findall('game'))==2
    assert out.findtext('name')=='Titre propre' and out.findtext('desc')=='Texte & accents é'
    assert out.findtext('image')==str(windows/'images/jeu.png')
    assert out.findtext('video')==str(windows/'videos/jeu.mp4')
    assert out.findtext('manual')==str(windows/'manuals/jeu.pdf')
    assert out.findtext('thumbnail')==str(root/'external/box.png')
    assert out.findtext('marquee')=='https://example.test/logo.png'
    assert out.findtext('favorite')=='true' and out.findtext('playcount')=='3'
    assert out.findtext('lastplayed')=='20261118' and out.find('hidden') is None
    assert out.findtext('custom')=='keep' and out.findtext('path')=='./Jeu [abc].sh'
    assert out.get('id') is None and src.read_bytes()==solo_before and game.read_bytes()==b'ROM'
    assert (party/'gamelist.xml.partydeck-before').read_bytes()==destination_before
    snapshot=dest.read_bytes()
    assert profiles.sync_library_scrapes(base,party)==0 and dest.read_bytes()==snapshot
    # Changed Windows scraps refresh on next import; no media files copied.
    g.find('desc').text='Nouvelle description';ET.ElementTree(source).write(src,encoding='utf-8')
    assert profiles.sync_library_scrapes(base,party)==1
    assert ET.parse(dest).findtext('.//desc')=='Nouvelle description'
    assert not (party/'images').exists()
    assert (party/'gamelist.xml.partydeck-before').read_bytes()==destination_before
    # Symlink alias works; a same-title other archive never matches.
    alias=windows/'alias.wsquashfs';alias.symlink_to(game)
    assert profiles.source_scrape(alias,{})[1].findtext('name')=='Titre propre'
    other=windows/'Jeu & test.wsquashfs';other.write_bytes(b'OTHER')
    assert profiles.source_scrape(other,{}) is None
    # Live ES receives only the Party path + scraped metadata, no stale counts.
    g.find('name').text='Nom actualisé';ET.ElementTree(source).write(src,encoding='utf-8')
    response=Mock(status=200);response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
    with patch.object(profiles,'PARTY_ROMS',party),patch.object(profiles,'urlopen',return_value=response) as request:
        assert profiles.sync_library_scrapes(base,party)==1
        payload=ET.fromstring(request.call_args.args[0].data)
        assert payload.findtext('game/path')=='./Jeu [abc].sh'
        assert payload.findtext('game/name')=='Nom actualisé'
        assert payload.find('game/playcount') is None and payload.find('game/favorite') is None
        assert request.call_args.kwargs['timeout']==2
    # Older/no API falls back to atomic gamelist update.
    with patch.object(profiles,'PARTY_ROMS',party),patch.object(profiles,'urlopen',side_effect=OSError('offline')):
        assert profiles.sync_library_scrapes(base,party)==1
    snapshot=dest.read_bytes();src.write_text('<broken')
    assert profiles.inherit_scrapes([(game,entry)],party)==0 and dest.read_bytes()==snapshot
    src.write_bytes(solo_before);dest.write_text('<invalid')
    assert profiles.inherit_scrapes([(game,entry)],party)==0 and dest.read_text()=='<invalid'
    dest.unlink();external=root/'personal.xml';external.write_text('<gameList/>');dest.symlink_to(external)
    assert profiles.inherit_scrapes([(game,entry)],party)==0 and external.read_text()=='<gameList/>'

with tempfile.TemporaryDirectory() as temp:
    root=Path(temp);windows=root/'windows';windows.mkdir();party=root/'party'
    base=root/'system';base.mkdir();source=ET.Element('gameList');pairs=[]
    for suffix in ('.wine','.pc','.wsquashfs'):
        rom=windows/('Game'+suffix)
        if suffix=='.wsquashfs':rom.write_bytes(b'ROM')
        else:rom.mkdir()
        game=ET.SubElement(source,'game');ET.SubElement(game,'path').text='./'+rom.name
        ET.SubElement(game,'name').text='Scrap '+suffix
        entry=party/(rom.name+'.sh');pairs.append((rom,entry))
        party.mkdir(exist_ok=True)
        entry.write_text('#!/bin/bash\n'+profiles.MARKER+'\nexec '+__import__('shlex').join([str(base/'windows-party'),'profil',str(rom)])+'\n')
    ET.ElementTree(source).write(windows/'gamelist.xml',encoding='utf-8')
    # The installer catches up every managed entry without touching custom ones.
    (party/'custom.sh').write_text('echo custom\n')
    profiles.install_menu(base,party)
    games=ET.parse(party/'gamelist.xml').findall('game')
    assert len(games)==3 and {g.findtext('name') for g in games}=={'Scrap .wine','Scrap .pc','Scrap .wsquashfs'}
    assert (party/'custom.sh').read_text()=='echo custom\n'

for language in ('fr','en'):
    set_language(language)
    value=tr('Scraps Windows repris pour {p0} jeu(x), sans copier les médias.',p0=2)
    assert '2' in value and ('Windows scraped metadata' in value if language=='en' else 'Scraps Windows' in value)
print('Scraps : chemins Windows, descriptions, médias sans copie, statistiques locales, migration et API ES vérifiés.')
