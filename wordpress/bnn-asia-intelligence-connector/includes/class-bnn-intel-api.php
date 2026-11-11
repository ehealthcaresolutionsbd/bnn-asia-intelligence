<?php
/**
 * Server-side API client with transient caching. The API key never reaches the browser.
 */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class BNN_Intel_API {

	/** Only these API paths may be requested through the public proxy. */
	const ALLOWED = array(
		'#^config/$#',
		'#^categories/$#',
		'#^indicators/$#',
		'#^countries/$#',
		'#^countries/[a-z0-9-]+/profile/$#',
		'#^incidents/$#',
		'#^ranking/$#',
		'#^official-rankings/$#',
		'#^compare/$#',
		'#^methodology/$#',
	);

	/** Allowed query parameters (anything else is dropped). */
	const PARAMS = array( 'period', 'category', 'indicator', 'countries', 'indicators', 'country__slug', 'incident_type__slug', 'limit', 'offset', 'region__slug' );

	public static function settings() {
		return wp_parse_args(
			get_option( 'bnn_intel_settings', array() ),
			array(
				'api_base'  => 'https://api.bnnasia.org/api/v1/',
				'api_key'   => '',
				'cache_ttl' => 600,
				'country_base' => 'country-intelligence',
			)
		);
	}

	public static function is_allowed( $path ) {
		foreach ( self::ALLOWED as $re ) {
			if ( preg_match( $re, $path ) ) {
				return true;
			}
		}
		return false;
	}

	/**
	 * @return array|WP_Error decoded JSON.
	 */
	public static function get( $path, $params = array() ) {
		$path = ltrim( (string) $path, '/' );
		if ( ! self::is_allowed( $path ) ) {
			return new WP_Error( 'bnn_intel_path', 'Path not allowed', array( 'status' => 400 ) );
		}
		$params = array_intersect_key( (array) $params, array_flip( self::PARAMS ) );
		$params = array_map( 'sanitize_text_field', $params );
		ksort( $params );
		$s    = self::settings();
		$url  = trailingslashit( $s['api_base'] ) . $path . ( $params ? '?' . http_build_query( $params ) : '' );
		$key  = 'bnn_intel_' . md5( $url );
		$hit  = get_transient( $key );
		if ( false !== $hit ) {
			return $hit;
		}
		$headers = array( 'Accept' => 'application/json' );
		if ( ! empty( $s['api_key'] ) ) {
			$headers['Authorization'] = 'Api-Key ' . $s['api_key'];
		}
		$res = wp_remote_get( $url, array( 'timeout' => 12, 'headers' => $headers ) );
		if ( is_wp_error( $res ) ) {
			return self::stale_or_error( $key, $res );
		}
		$code = wp_remote_retrieve_response_code( $res );
		$data = json_decode( wp_remote_retrieve_body( $res ), true );
		if ( 200 !== $code || ! is_array( $data ) ) {
			return self::stale_or_error( $key, new WP_Error( 'bnn_intel_http', 'API returned HTTP ' . $code, array( 'status' => 502 ) ) );
		}
		set_transient( $key, $data, (int) $s['cache_ttl'] );
		update_option( $key . '_stale', $data, false ); // last good copy for outages
		return $data;
	}

	private static function stale_or_error( $key, $err ) {
		$stale = get_option( $key . '_stale' );
		return $stale ? $stale : $err;
	}

	public static function flush_cache() {
		global $wpdb;
		$wpdb->query( "DELETE FROM {$wpdb->options} WHERE option_name LIKE '\_transient\_bnn\_intel\_%' OR option_name LIKE '\_transient\_timeout\_bnn\_intel\_%'" );
	}
}
