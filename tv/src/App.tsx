/**
 * Catch-Up 60 — Fire TV app.
 *
 * Press Catch Up and the app fetches a recap of the game as it stands right
 * now, then plays it: one card per play, animated against a clock, ending at
 * the live edge.
 *
 * The clock is the manifest's, not the audio element's. Two reasons, both
 * learned the hard way on the Vega Virtual Device:
 *
 *   - the VVD's audio sink does not initialize. The decoder reaches `playing`
 *     and then errors, and the device log shows "leaudiosink ... Failed to
 *     create streamhelper object" and "sink not negotiated" with no codec
 *     error anywhere. A standard mp3 from a public origin fails identically,
 *     so it is the simulator, not the content.
 *   - `currentTime` reads NaN on that path, so there is nothing to sync to.
 *
 * Driving the animation from the manifest keeps the recap correct everywhere
 * and lets audio ride along where the hardware supports it. The manifest's
 * segment timings come from the real synthesized audio, so the two agree.
 */
import React, {useCallback, useEffect, useRef, useState} from 'react';
import {
  Animated,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import {TVFocusGuideView} from '@amazon-devices/react-native-kepler';

const HOST = '10.0.2.2';
// JSON over http and audio over https is not an oversight. Vega's media player
// refuses http:// outright ("isUriSchemeSecure ... insecure protocol/scheme
// http"), while fetch() rejects our development certificate. In production both
// are https from one trusted origin.
const API = `http://${HOST}:8080`;

type Segment = {
  kind: 'intro' | 'play' | 'outro';
  text: string;
  start: number;
  dur: number;
  playIndex?: number;
};

type Manifest = {
  away: string;
  home: string;
  awayName: string;
  homeName: string;
  gameState: {inning: number; half: string; away: number; home: number};
  totalSeconds: number;
  audioUrl: string | null;
  segments: Segment[];
  engine: {selected: number; runsExplained: number; runsTotal: number};
};

type Phase = 'idle' | 'loading' | 'playing' | 'done' | 'error';

export const App = () => {
  const [phase, setPhase] = useState<Phase>('idle');
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [position, setPosition] = useState(0);
  const [note, setNote] = useState<string>('');
  const fade = useRef(new Animated.Value(0)).current;
  const rise = useRef(new Animated.Value(0)).current;
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  const clearTimers = useCallback(() => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  }, []);

  useEffect(() => clearTimers, [clearTimers]);

  const animateIn = useCallback(() => {
    fade.setValue(0);
    rise.setValue(14);
    Animated.parallel([
      Animated.timing(fade, {
        toValue: 1,
        duration: 260,
        useNativeDriver: true,
      }),
      Animated.timing(rise, {
        toValue: 0,
        duration: 260,
        useNativeDriver: true,
      }),
    ]).start();
  }, [fade, rise]);

  const catchUp = useCallback(async () => {
    clearTimers();
    setPhase('loading');
    setNote('');
    try {
      const response = await fetch(`${API}/recap/synthetic`);
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        setNote(body.error ?? `HTTP ${response.status}`);
        setPhase('error');
        return;
      }
      const data: Manifest = await response.json();
      setManifest(data);
      setPosition(0);
      setPhase('playing');
      animateIn();

      // One timer per segment boundary, from the manifest's own timings.
      data.segments.forEach((segment, index) => {
        if (index === 0) {
          return;
        }
        timers.current.push(
          setTimeout(() => {
            setPosition(index);
            animateIn();
          }, segment.start * 1000),
        );
      });
      timers.current.push(
        setTimeout(() => setPhase('done'), data.totalSeconds * 1000),
      );

      // Audio rides along when the platform can play it. Failure is expected
      // on the simulator and must not interrupt the recap.
      if (data.audioUrl) {
        void attachAudio(data.audioUrl.replace(`http://${HOST}:8080`,
                                               `https://${HOST}:8443`));
      }
    } catch (error: any) {
      setNote(`${error?.message ?? error}`);
      setPhase('error');
    }
  }, [animateIn, clearTimers]);

  const attachAudio = async (url: string) => {
    try {
      const {AudioPlayer} = await import(
        '@amazon-devices/react-native-w3cmedia'
      );
      const player = new AudioPlayer();
      await player.initialize();
      player.addEventListener('error', () =>
        setNote('audio unavailable on this device — cards still in sync'),
      );
      (player as any).src = url;
      (player as any).autoplay = false;
      await player.play();
    } catch {
      setNote('audio unavailable on this device — cards still in sync');
    }
  };

  const segment = manifest?.segments[position];
  const progress = manifest && segment
    ? Math.min(1, (segment.start + segment.dur) / manifest.totalSeconds)
    : 0;

  return (
    <View style={styles.screen}>
      <View style={styles.header}>
        <Text style={styles.brand}>Catch-Up 60</Text>
        {manifest && (
          <Text style={styles.score}>
            {manifest.away} {manifest.gameState.away} · {manifest.home}{' '}
            {manifest.gameState.home} — {manifest.gameState.half}{' '}
            {manifest.gameState.inning}
          </Text>
        )}
      </View>

      {phase === 'idle' && (
        <TVFocusGuideView style={styles.center} autoFocus>
          <Pressable
            hasTVPreferredFocus
            onPress={catchUp}
            style={({focused}) => [styles.button, focused && styles.focused]}>
            {({focused}) => (
              <Text style={[styles.buttonText, focused && styles.buttonTextOn]}>
                Catch Up
              </Text>
            )}
          </Pressable>
          <Text style={styles.hint}>
            Sixty seconds on how the game got here
          </Text>
        </TVFocusGuideView>
      )}

      {phase === 'loading' && (
        <View style={styles.center}>
          <Text style={styles.hint}>Building your recap…</Text>
        </View>
      )}

      {phase === 'playing' && segment && (
        <View style={styles.cardArea}>
          <Animated.View
            style={[
              styles.card,
              {opacity: fade, transform: [{translateY: rise}]},
            ]}>
            <Text style={styles.kind}>
              {segment.kind === 'play' ? 'What you missed' : segment.kind}
            </Text>
            <Text style={styles.cardText}>{segment.text}</Text>
          </Animated.View>
          <View style={styles.track}>
            <View style={[styles.fill, {flex: progress}]} />
            <View style={{flex: 1 - progress}} />
          </View>
        </View>
      )}

      {phase === 'done' && (
        <View style={styles.center}>
          <Text style={styles.done}>You're caught up. Back to live.</Text>
          <Pressable
            hasTVPreferredFocus
            onPress={catchUp}
            style={({focused}) => [styles.button, focused && styles.focused]}>
            {({focused}) => (
              <Text style={[styles.buttonText, focused && styles.buttonTextOn]}>
                Again
              </Text>
            )}
          </Pressable>
        </View>
      )}

      {phase === 'error' && (
        <View style={styles.center}>
          <Text style={styles.error}>{note || 'Could not build a recap'}</Text>
        </View>
      )}

      {note !== '' && phase === 'playing' && (
        <Text style={styles.footnote}>{note}</Text>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  screen: {flex: 1, backgroundColor: '#07090f', paddingHorizontal: 64,
           paddingVertical: 48},
  header: {flexDirection: 'row', alignItems: 'baseline', gap: 24},
  brand: {color: '#f0f6fc', fontSize: 30, fontWeight: '700',
          letterSpacing: 0.5},
  score: {color: '#8b949e', fontSize: 22},
  center: {flex: 1, alignItems: 'center', justifyContent: 'center', gap: 24},
  button: {paddingHorizontal: 56, paddingVertical: 22, borderRadius: 10,
           backgroundColor: '#161b22', borderWidth: 2,
           borderColor: '#30363d'},
  focused: {backgroundColor: '#f0f6fc', borderColor: '#f0f6fc',
            transform: [{scale: 1.04}]},
  buttonText: {color: '#f0f6fc', fontSize: 30, fontWeight: '600'},
  buttonTextOn: {color: '#07090f'},
  hint: {color: '#6e7681', fontSize: 20},
  cardArea: {flex: 1, justifyContent: 'center', gap: 40},
  card: {backgroundColor: '#0d1117', borderLeftWidth: 5,
         borderLeftColor: '#2f81f7', borderRadius: 8, padding: 36},
  kind: {color: '#2f81f7', fontSize: 16, fontWeight: '700',
         letterSpacing: 1.6, textTransform: 'uppercase', marginBottom: 14},
  cardText: {color: '#f0f6fc', fontSize: 34, lineHeight: 46},
  track: {flexDirection: 'row', height: 5, backgroundColor: '#161b22',
          borderRadius: 3, overflow: 'hidden'},
  fill: {backgroundColor: '#2f81f7'},
  done: {color: '#f0f6fc', fontSize: 34},
  error: {color: '#ff7b72', fontSize: 24, textAlign: 'center'},
  footnote: {color: '#6e7681', fontSize: 16},
});
